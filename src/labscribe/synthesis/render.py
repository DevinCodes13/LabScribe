"""Render generated Markdown to HTML for the review screen.

Rendering happens server-side with the `markdown` library so the review pane
is reliable inside the packaged app (no external JS/CDN). Mermaid diagrams
(M4) are left as fenced code blocks for now — they'll render on GitHub, and
we can add a client-side mermaid renderer to the review pane in a later pass.
"""

import markdown as _md


def render_markdown(text: str) -> str:
    return _md.markdown(
        text,
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
        output_format="html5",
    )
