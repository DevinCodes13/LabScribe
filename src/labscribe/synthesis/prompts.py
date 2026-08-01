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
"""

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
   in the order it happened. Reference screenshots by their filename at the right \
   point, like "(see `2026-07-31_2141_dcpromo.png`)".
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


def build_user_message(session: dict, transcripts: list[dict], screenshots: list[str],
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

    # Screenshots (filenames only)
    parts.append("## Screenshot filenames")
    if screenshots:
        parts.extend(f"- {name}" for name in screenshots)
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
            body = t["text"]
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
