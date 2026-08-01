"""Run an nmap sweep of the lab subnet and parse the results.

Design decisions worth understanding:

  - nmap is an EXTERNAL program the user installs separately (it is not bundled).
    So everything here is written to degrade gracefully: if nmap isn't on PATH,
    we say so and the caller falls back to a config-only diagram.
  - We use a TCP connect scan (-sT) with a fast top-ports profile (-F). Connect
    scans don't need Administrator/Npcap-raw-socket privileges, so the app can
    scan without being run as admin. A SYN scan would be faster but requires
    elevation, which conflicts with "just double-click the .exe".
  - We ask nmap for XML on stdout (-oX -) and parse it with python-libnmap, so
    we never scrape human-readable output.
  - On Windows we pass CREATE_NO_WINDOW so the packaged GUI app doesn't flash a
    console window when it shells out to nmap.

Scope note: scanning is pointed at the user's own isolated lab subnet (from
Settings) — lab-only, per the project's constraints.
"""

import shutil
import subprocess
import sys

from libnmap.parser import NmapParser


class ScanError(Exception):
    """User-facing scan problem (nmap missing, timeout, bad subnet)."""


# Windows: don't flash a console window when shelling out from the GUI app.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def nmap_path() -> str | None:
    return shutil.which("nmap")


def nmap_available() -> bool:
    return nmap_path() is not None


def scan(subnet: str, timeout: int = 300) -> list[dict]:
    """Scan `subnet` and return a list of live hosts.

    Each host: {ip, hostname, state, ports: [{port, proto, service, state}]}.
    Raises ScanError with a clear message on any failure.
    """
    exe = nmap_path()
    if not exe:
        raise ScanError(
            "nmap is not installed. Install it from https://nmap.org/download "
            "(include Npcap) to scan the live lab, or use Build from inventory."
        )
    subnet = subnet.strip()
    if not subnet:
        raise ScanError("No lab subnet set. Add it in Settings first.")

    # -sT connect scan (no admin needed) · -T4 fast timing · -F top-100 ports
    # -Pn skip host-discovery ping (lab hosts may not answer ICMP) · XML to stdout
    cmd = [exe, "-sT", "-T4", "-F", "-Pn", "-oX", "-", subnet]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise ScanError(f"nmap scan timed out after {timeout}s. Try a smaller subnet.")
    except OSError as e:
        raise ScanError(f"Couldn't run nmap: {e}")

    if proc.returncode != 0 and not proc.stdout.strip():
        msg = (proc.stderr or "unknown error").strip().splitlines()[-1]
        raise ScanError(f"nmap failed: {msg}")

    try:
        report = NmapParser.parse(proc.stdout)
    except Exception as e:
        raise ScanError(f"Couldn't parse nmap output: {e}")

    hosts: list[dict] = []
    for h in report.hosts:
        if h.status != "up":
            continue
        ports = []
        for p in h.get_open_ports():
            svc = h.get_service(p[0], protocol=p[1])
            ports.append({
                "port": p[0],
                "proto": p[1],
                "service": (svc.service if svc else "") or "",
                "state": "open",
            })
        hostname = h.hostnames[0] if h.hostnames else ""
        hosts.append({
            "ip": h.address,
            "hostname": hostname,
            "state": h.status,
            "ports": sorted(ports, key=lambda x: x["port"]),
        })
    return hosts
