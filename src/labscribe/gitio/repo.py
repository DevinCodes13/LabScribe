"""Git integration: commit reviewed docs into the user's repo (spec §5, §8, §11).

Guardrails that shape this module:
  - Human-in-the-loop (R6): nothing here runs on its own. The review screen's
    Commit button (or the opt-in auto-commit setting) triggers it explicitly.
  - Secrets never committed (R4/§11): before writing anything we run a secret
    scan over the exact bytes to be committed. Any high-confidence key pattern
    BLOCKS the commit — the user redacts in the review editor and retries. This
    is a safety net behind the model's own redaction, not a replacement.
  - We never log or echo a matched secret in full — only a masked preview.

What gets committed:
  - README.md            <- the reviewed markdown (the generated doc IS a full
                            README in the target format)
  - CHANGELOG.md         <- one dated line appended per commit, so the per-session
                            history survives even though README.md is a snapshot
"""

import re
from datetime import date
from pathlib import Path

try:
    import git  # GitPython
except Exception:  # pragma: no cover - import guarded so the app still starts
    git = None


class RepoError(Exception):
    """User-facing git problem (no repo, secrets found, nothing to commit)."""


# High-signal secret patterns only — chosen to almost never fire on legitimate
# lab documentation (prose like "set the Administrator password" won't match),
# while catching real credentials that leaked into a transcript unredacted.
_SECRET_PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


def _mask(token: str) -> str:
    """Show enough to locate the secret without printing it: 'sk-a…***'."""
    head = token[:4]
    return f"{head}…***"


def secret_scan(text: str) -> list[dict]:
    """Return a list of {type, line, preview} for any secret-like matches."""
    findings: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in _SECRET_PATTERNS:
            for m in pattern.finditer(line):
                findings.append({
                    "type": name,
                    "line": lineno,
                    "preview": _mask(m.group(0)),
                })
    return findings


def _open_repo(repo_path: str):
    if git is None:
        raise RepoError("GitPython isn't available in this build.")
    if not repo_path.strip():
        raise RepoError("No repo path set. Add your local repo path in Settings first.")
    path = Path(repo_path)
    if not path.exists():
        raise RepoError(f"Repo path does not exist: {repo_path}")
    try:
        return git.Repo(path)
    except git.InvalidGitRepositoryError:
        raise RepoError(
            f"'{repo_path}' is not a git repository. Point Settings at your cloned "
            "repo, or run `git init` there once."
        )
    except git.NoSuchPathError:
        raise RepoError(f"Repo path does not exist: {repo_path}")


def repo_status(repo_path: str) -> dict:
    """Lightweight state for the UI: does the path exist, is it a repo, branch."""
    info = {"path": repo_path, "exists": False, "is_repo": False, "branch": None}
    if not repo_path.strip():
        return info
    path = Path(repo_path)
    info["exists"] = path.exists()
    if not info["exists"] or git is None:
        return info
    try:
        repo = git.Repo(path)
        info["is_repo"] = True
        try:
            info["branch"] = repo.active_branch.name
        except TypeError:
            info["branch"] = "(detached)"
    except Exception:
        info["is_repo"] = False
    return info


def _append_changelog(repo_dir: Path, session: dict) -> Path:
    """Append one dated entry to CHANGELOG.md (newest first, under the header)."""
    changelog = repo_dir / "CHANGELOG.md"
    header = "# Changelog\n\n"
    counts = session.get("counts") or {}
    parts = []
    if counts:
        parts.append(f"{counts.get('transcripts', 0)} transcripts")
        parts.append(f"{counts.get('screenshots', 0)} screenshots")
        parts.append(f"{counts.get('notes', 0)} notes")
    detail = f" ({', '.join(parts)})" if parts else ""
    entry = f'- {date.today().isoformat()} — Documented session "{session.get("name", "Untitled")}"{detail}\n'

    if changelog.exists():
        existing = changelog.read_text(encoding="utf-8")
        if existing.startswith("# Changelog"):
            # Insert the new entry right after the header block.
            body = existing[len(header):] if existing.startswith(header) else \
                existing.split("\n", 1)[1] if "\n" in existing else ""
            changelog.write_text(header + entry + body, encoding="utf-8")
        else:
            changelog.write_text(header + entry + "\n" + existing, encoding="utf-8")
    else:
        changelog.write_text(header + entry, encoding="utf-8")
    return changelog


def commit_docs(session: dict, markdown: str, repo_path: str) -> dict:
    """Secret-scan, write README.md + CHANGELOG.md, and commit.

    Raises RepoError (with structured secret findings when applicable) on any
    problem so nothing partial is committed.
    """
    repo = _open_repo(repo_path)
    repo_dir = Path(repo.working_tree_dir)

    # 1. Secret scan — block the commit if anything key-like is present.
    findings = secret_scan(markdown)
    if findings:
        err = RepoError(
            "Commit blocked: possible secrets found in the document. Redact them "
            "in the review editor and try again."
        )
        err.findings = findings  # attached for the API to surface
        raise err

    # 2. Write files.
    readme = repo_dir / "README.md"
    readme.write_text(markdown, encoding="utf-8")
    changelog = _append_changelog(repo_dir, session)

    # 3. Stage + commit.
    rel = [str(readme.relative_to(repo_dir)), str(changelog.relative_to(repo_dir))]
    repo.index.add(rel)
    if not repo.is_dirty(index=True, working_tree=False):
        raise RepoError("Nothing changed since the last commit.")
    message = f'docs: {session.get("name", "lab session")} (LabScribe)'
    commit = repo.index.commit(message)

    return {
        "committed": True,
        "commit": commit.hexsha[:10],
        "message": message,
        "files": rel,
        "branch": (repo.active_branch.name
                   if not repo.head.is_detached else "(detached)"),
    }
