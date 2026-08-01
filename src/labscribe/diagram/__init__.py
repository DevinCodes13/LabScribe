"""Diagram generation: persist the latest network diagram and refresh it.

The latest diagram is saved next to the .env file so it survives restarts and
can be embedded into the generated README (M3 synthesis reads it from here).
"""

from datetime import datetime

from labscribe.capture import orchestrator
from labscribe.config import settings
from labscribe.diagram import mermaid, nmap_scan

TIME_FMT = orchestrator.TIME_FMT


def _diagram_path():
    d = settings.env_path().parent / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d / "network.mmd"


def get_diagram() -> str | None:
    p = _diagram_path()
    return p.read_text(encoding="utf-8") if p.exists() else None


def save_diagram(text: str) -> None:
    _diagram_path().write_text(text, encoding="utf-8")


def config_diagram(subnet: str) -> str:
    """A config-only diagram — always available, no nmap needed."""
    text, _ = mermaid.build(subnet, scan_hosts=None)
    return text


def diagram_for_readme(subnet: str) -> str:
    """The diagram to embed in the generated README: the last refreshed one if
    present, otherwise a config-only diagram built from the subnet."""
    return get_diagram() or config_diagram(subnet)


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
    save_diagram(text)
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
