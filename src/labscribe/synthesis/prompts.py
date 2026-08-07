"""System prompt and message construction for the synthesis engine.

The system prompt tells the model exactly how to turn raw capture material
(terminal transcripts, quick notes, screenshot filenames) into README markdown
in the user's target format. The target format template is injected at the
{{TEMPLATE}} marker so the model matches the user's existing structure.

Design notes for the reader:
  - Section 4 (Troubleshooting Log) is the highest-value output, so the prompt
    puts the most weight there: infer problem -> cause -> fix from errors that
    appear in the transcript output, not just from the commands run.
  - The prompt is explicit that this is an isolated lab the user owns, so the
    model treats attack/detection content as legitimate documentation.
  - It must never invent facts. If something isn't in the material, it says so
    rather than fabricating IPs, versions, or steps.

Cost note: raw `script`-captured Linux transcripts are full of ANSI/VT100
terminal escape codes (cursor moves, redraws, color) — pure noise for the
model, and pure token cost. _strip_terminal_codes() removes them before the
transcript ever reaches the prompt, which both shrinks the request and stops
the model from having to parse through garbage to find the real content.
"""

import re

# CSI sequences (\x1b[...letter, e.g. \x1b[?25l, \x1b[32m) and OSC sequences
# (\x1b]...BEL, e.g. window-title-setting) — the two escape families `script`
# actually emits when it records a real interactive terminal session.
_CSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_OSC = re.compile(r"\x1b\][0-9;]*.*?(?:\x07|\x1b\\)")
_OTHER_ESC = re.compile(r"\x1b[()][A-Za-z0-9]|\x1b[=>]")


def _strip_terminal_codes(text: str) -> str:
    text = _CSI.sub("", text)
    text = _OSC.sub("", text)
    text = _OTHER_ESC.sub("", text)
    # Collapse the runs of blank lines this often leaves behind.
    return re.sub(r"\n{3,}", "\n\n", text)

SYSTEM_PROMPT = """\
You are LabScribe's documentation writer. You turn raw capture material from a \
home cybersecurity lab into clean, accurate GitHub README documentation.

CONTEXT
The user is building an isolated home lab they own, in VirtualBox, for learning \
defensive security (a domain controller, a Windows workstation, an Ubuntu/Splunk \
SIEM, and a Kali attacker box). All attack and detection content is authorized, \
educational, and for their own isolated network. Document it plainly and \
professionally, the way a SOC analyst's lab notebook would.

YOUR INPUT
You receive, for a single work session:
  - Terminal transcripts (the commands the user ran and the output those commands \
    produced) from one or more lab machines.
  - Quick notes the user jotted, each timestamped.
  - The filenames of screenshots the user captured (you cannot see the images, \
    only the names).

YOUR JOB
Produce a single Markdown document that matches the TARGET FORMAT below. Populate \
every section you have material for. For sections you have no material for, keep \
the heading and write a short italic placeholder like *No activity captured for \
this section yet.* — never delete a section, never invent content to fill it.

RULES
1. Accuracy over completeness. Only state things supported by the transcripts or \
   notes. Do not invent IP addresses, hostnames, versions, or steps. If a detail \
   is implied but not certain, hedge ("appears to", "likely").
2. The Troubleshooting Log is the most important section. Read the transcript \
   OUTPUT (not just the commands) for errors, failures, and warnings, and turn \
   each into an Issue / Cause / Fix row — inferring the cause and the fix the \
   user applied from what happened next in the transcript. This is where you add \
   the most value.
3. Build Steps: per machine, summarize what was configured and *why it matters*, \
   in the order it happened. Every screenshot you're given comes with the exact \
   timestamp it was taken — use it to find the closest point in the transcript \
   timeline and cite it there, like "(see `2026-07-31_2141_dcpromo.png`)". This is \
   a hard requirement, not a suggestion: every screenshot filename you were given \
   MUST appear at least once somewhere in the document. If you genuinely can't tell \
   which specific step a screenshot belongs to, still list it under that machine's \
   Build Steps section (e.g. "Additional screenshots from this session: \
   `filename.png`") rather than silently dropping it.
4. Never include secrets. If a password, API key, hash, or token appears in the \
   raw material, replace it with `[REDACTED]` in your output. Never echo an \
   Anthropic API key.
5. The Network Diagram section already contains the correct Mermaid diagram. \
   Reproduce that ```mermaid block EXACTLY as given — do not edit, relabel, or \
   regenerate it. It was produced from the real lab configuration/scan.
6. Output ONLY the Markdown document. No preamble, no explanation, no code fence \
   around the whole thing.

TARGET FORMAT
{{TEMPLATE}}
"""


def build_user_message(session: dict, transcripts: list[dict], screenshots: list[dict],
                       notes: list[str], lab_subnet: str, max_chars: int) -> str:
    """Assemble the raw capture material into a single user message.

    Transcript text is capped at max_chars total so a very long session can't
    blow past a reasonable request size; if we hit the cap we say so explicitly
    so the model knows the material was truncated.
    """
    parts: list[str] = []
    parts.append(f"# Session: {session.get('name', 'Untitled')}")
    parts.append(f"Started: {session.get('started_at', '?')}   "
                 f"Ended: {session.get('ended_at') or 'still running'}")
    parts.append(f"Lab subnet: {lab_subnet}")
    parts.append("")

    # Notes
    parts.append("## Quick notes")
    if notes:
        parts.extend(notes)
    else:
        parts.append("(none)")
    parts.append("")

    # Screenshots, timestamped and in chronological order so the model can line
    # each one up against the point in the transcript where it was taken.
    parts.append("## Screenshots (chronological — cite every one of these filenames "
                 "somewhere in Build Steps, placed near its matching timestamp)")
    if screenshots:
        parts.extend(
            f"- [{s['taken_at'].strftime('%Y-%m-%d %H:%M:%S')}] {s['name']}"
            for s in screenshots
        )
    else:
        parts.append("(none)")
    parts.append("")

    # Transcripts, with a shared character budget
    parts.append("## Terminal transcripts")
    if not transcripts:
        parts.append("(none)")
    else:
        budget = max_chars
        for t in transcripts:
            header = f"\n----- transcript: {t['name']} -----\n"
            body = _strip_terminal_codes(t["text"])
            if len(body) > budget:
                body = body[:budget] + "\n[...transcript truncated to fit size limit...]"
                budget = 0
            else:
                budget -= len(body)
            parts.append(header + body)
            if budget <= 0:
                parts.append("\n[...remaining transcripts omitted to fit size limit...]")
                break

    parts.append("")
    parts.append("Now write the README documentation for this session, following "
                 "the target format exactly.")
    return "\n".join(parts)
