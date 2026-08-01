"""Build a Mermaid network diagram from the lab inventory and/or an nmap scan.

The diagram's home is the README — GitHub renders ```mermaid blocks natively
(spec §7), so we emit Mermaid text rather than an image.

Two sources, matching the spec:
  - From config (always available): the known lab inventory below, laid out on
    the configured subnet.
  - From reality (preferred, needs nmap): merge the scan results in — mark each
    known host up/down, annotate a couple of open ports, and surface any
    unexpected live hosts the scan found.

The inventory is the canonical home-SOC lab (DC, workstation, SIEM, attacker).
Host IPs are derived from the configured subnet's /24 base with fixed last
octets, matching the spec's example (.10/.20/.30/.40).
"""

import ipaddress

# Known lab hosts, keyed by their last octet on the lab /24.
INVENTORY = [
    {"octet": 10, "node": "DC",   "name": "DC01",   "os": "Windows Server 2022",
     "role": "Domain Controller + DNS"},
    {"octet": 20, "node": "WKS",  "name": "WKS01",  "os": "Windows 11",
     "role": "Domain-joined workstation"},
    {"octet": 30, "node": "SIEM", "name": "SIEM01", "os": "Ubuntu + Splunk",
     "role": "SIEM / log collector"},
    {"octet": 40, "node": "KALI", "name": "KALI01", "os": "Kali Linux",
     "role": "Attacker"},
]

# Logical relationships (node_a, node_b, arrow, label). Dotted arrows (-.->) are
# attack paths; solid arrows are normal operations.
EDGES = [
    ("WKS", "DC", "-->", "authenticates / DNS"),
    ("DC", "SIEM", "-->", "forwards logs"),
    ("WKS", "SIEM", "-->", "forwards logs"),
    ("KALI", "DC", "-.->", "attacks"),
    ("KALI", "WKS", "-.->", "attacks"),
]


def network_base(subnet: str) -> str:
    """Return the first three octets of a subnet, e.g. '10.10.10.0/24' -> '10.10.10'."""
    subnet = (subnet or "").strip()
    try:
        net = ipaddress.ip_network(subnet, strict=False)
        return ".".join(str(net.network_address).split(".")[:3])
    except ValueError:
        # Best-effort fallback: strip any /mask and take the first three octets.
        parts = subnet.split("/")[0].split(".")
        if len(parts) >= 3:
            return ".".join(parts[:3])
        return "10.10.10"


def _label(item: dict, ip: str, extra: str = "") -> str:
    """Mermaid node label. <br/> makes multi-line boxes; quotes keep it safe."""
    lines = [item["name"], item["os"], item["role"], ip]
    if extra:
        lines.append(extra)
    return "<br/>".join(lines)


def build(subnet: str, scan_hosts: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Return (mermaid_text, host_rows).

    scan_hosts=None -> config-only diagram (every known host shown as assumed).
    Otherwise the scan is merged: known hosts are marked up/down with open ports,
    and unexpected live hosts are added as 'unknown' nodes.
    host_rows is a UI-friendly table of the hosts represented.
    """
    base = network_base(subnet)
    subnet_label = subnet.strip() or f"{base}.0/24"

    # Index scan results by IP for quick lookup.
    by_ip = {h["ip"]: h for h in (scan_hosts or [])}
    matched_ips: set[str] = set()

    lines: list[str] = ["graph TB"]
    lines.append(f'    subgraph LAB["Isolated Lab Network - {subnet_label}"]')

    rows: list[dict] = []
    for item in INVENTORY:
        ip = f"{base}.{item['octet']}"
        scanned = by_ip.get(ip)
        if scan_hosts is None:
            status, extra = "assumed", ""
            ports = []
        elif scanned:
            matched_ips.add(ip)
            ports = scanned["ports"]
            status = "up"
            top = ", ".join(str(p["port"]) for p in ports[:4]) if ports else "no open ports"
            extra = f"[UP] {top}"
        else:
            status, extra, ports = "down", "[not detected]", []

        lines.append(f'        {item["node"]}["{_label(item, ip, extra)}"]')
        rows.append({
            "name": item["name"], "ip": ip, "os": item["os"], "role": item["role"],
            "status": status,
            "ports": [f"{p['port']}/{p['proto']} {p['service']}".strip() for p in ports],
        })

    # Unexpected live hosts (in the scan but not in the known inventory).
    unknown_idx = 0
    for h in (scan_hosts or []):
        if h["ip"] in matched_ips:
            continue
        unknown_idx += 1
        node = f"UNK{unknown_idx}"
        last = h["ip"].split(".")[-1]
        top = ", ".join(str(p["port"]) for p in h["ports"][:4]) if h["ports"] else "no open ports"
        name = h["hostname"] or f"host .{last}"
        lines.append(f'        {node}["{name}<br/>unknown host<br/>{h["ip"]}<br/>[UP] {top}"]')
        rows.append({
            "name": name, "ip": h["ip"], "os": "unknown", "role": "unrecognized host",
            "status": "up",
            "ports": [f"{p['port']}/{p['proto']} {p['service']}".strip() for p in h["ports"]],
        })

    # Edges (only between known nodes, which always exist in the diagram).
    for a, b, arrow, label in EDGES:
        lines.append(f'        {a} {arrow}|"{label}"| {b}')

    lines.append("    end")
    return "\n".join(lines), rows


def fenced(mermaid_text: str) -> str:
    """Wrap the diagram in a ```mermaid fence for embedding in Markdown."""
    return f"```mermaid\n{mermaid_text}\n```"
