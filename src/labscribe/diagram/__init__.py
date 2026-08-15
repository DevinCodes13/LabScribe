"""Diagram generation: persist the latest network diagram and refresh it.

The latest diagram is saved next to the .env file so it survives restarts and
can be embedded into the generated README (M3 synthesis reads it from here).

Bug fix (2026-08): the cache used to be a single unscoped file, so once any
diagram was saved it got reused verbatim for every subsequent doc generation
regardless of which subnet/project the session actually belonged to — the
same diagram (and, via the template, the same host table) showed up for
every project. The cache now tags itself with the subnet it was built for;
diagram_for_readme() only reuses it when that subnet still matches the
session's current lab_subnet setting, otherwise it falls back to a fresh
config-only diagram for the current subnet.
"""

import re
from datetime import datetime

from labscribe.capture import orchestrator
from labscribe.config import settings
from labscribe.diagram import mermaid, nmap_scan

TIME_FMT = orchestrator.TIME_FMT

_SUBNET_TAG = re.compile(r"^%%\s*subnet:\s*(\S+)\s*\n", re.MULTILINE)


def _diagram_path():
    d = settings.env_path().parent / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d / "network.mmd"


def get_diagram(subnet: str | None = None) -> str | None:
    """Return the cached diagram.

    If `subnet` is given, the cache is only returned when it was built for
    that exact subnet — a diagram cached for one project's lab_subnet is
    never silently reused for a different one. Pass None (e.g. for the
    dashboard's "current diagram" view) to get whatever is cached regardless
    of subnet.
    """
    p = _diagram_path()
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    m = _SUBNET_TAG.match(text)
    cached_subnet = m.group(1) if m else None
    if subnet is not None and cached_subnet != subnet:
        return None
    return text[m.end():] if m else text


def save_diagram(text: str, subnet: str) -> None:
    _diagram_path().write_text(f"%% subnet: {subnet}\n{text}", encoding="utf-8")


def config_diagram(subnet: str) -> str:
    """A config-only diagram — always available, no nmap needed."""
    text, _ = mermaid.build(subnet, scan_hosts=None)
    return text


def diagram_for_readme(subnet: str) -> str:
    """The diagram to embed in the generated README: the last refreshed one if
    it was built for this exact subnet, otherwise a fresh config-only diagram
    for the current subnet (never a stale diagram from a different project)."""
    return get_diagram(subnet) or config_diagram(subnet)


def refresh(mode: str = "scan") -> dict:
    """Build and save a fresh diagram.

    mode="scan"      -> nmap sweep merged with inventory (raises ScanError if
                        nmap is missing or the scan fails)
    mode="config"    -> inventory-only, no scan
    """
    cfg = settings.get_settings()
    subnet = cfg["lab_subnet"]

    if mode == "scan":
        scan_hosts = nmap_scan.scan(subnet)  # raises ScanError on failure
    else:
        scan_hosts = None

    text, rows = mermaid.build(subnet, scan_hosts=scan_hosts)
    save_diagram(text, subnet)
    return {
        "mermaid": text,
        "hosts": rows,
        "mode": mode,
        "subnet": subnet,
        "nmap_available": nmap_scan.nmap_available(),
        "refreshed_at": datetime.now().strftime(TIME_FMT),
    }


def current() -> dict:
    """Return the saved diagram (or a fresh config-only one) for display."""
    cfg = settings.get_settings()
    subnet = cfg["lab_subnet"]
    text = get_diagram()
    if text is None:
        text, rows = mermaid.build(subnet, scan_hosts=None)
    else:
        # The saved .mmd is the source of truth for the diagram; rebuild a
        # config view purely to populate the host table shown beside it.
        _, rows = mermaid.build(subnet, scan_hosts=None)
    return {
        "mermaid": text,
        "hosts": rows,
        "subnet": subnet,
        "nmap_available": nmap_scan.nmap_available(),
    }
