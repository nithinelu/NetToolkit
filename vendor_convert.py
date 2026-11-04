#!/usr/bin/env python3
"""
Multi-vendor switch configuration converter
===========================================

Translates a switch configuration between vendor CLIs by parsing it into a
neutral intermediate model and re-generating it in the target syntax.

Supported vendors:
    cisco   - Cisco IOS / IOS-XE
    arista  - Arista EOS
    aruba   - Aruba AOS-CX
    huawei  - Huawei VRP
    hp      - HPE Comware (H3C)

IMPORTANT - this is a best-effort translator for the COMMON constructs:
hostname, VLANs + names, interface descriptions, access/trunk switchports
(access VLAN, native/PVID, allowed VLANs), L3 IP addresses, and admin state.
Anything it does not recognise is preserved verbatim at the end of the output
as commented "unconverted" lines, so nothing is silently lost. Interface names
are kept as-is (naming differs per platform) - review them before applying.

CLI::

    python vendor_convert.py --from cisco --to huawei input.txt -o out.txt
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

VENDORS = ["cisco", "arista", "aruba", "huawei", "hp"]
VENDOR_LABELS = {
    "cisco": "Cisco IOS / IOS-XE",
    "arista": "Arista EOS",
    "aruba": "Aruba AOS-CX",
    "huawei": "Huawei VRP",
    "hp": "HPE Comware (H3C)",
}

AllowedVlans = Union[str, List[int], None]  # "all", list of ids, or None


# ===========================================================================
# Intermediate model helpers
# ===========================================================================
def _new_iface(name: str) -> Dict[str, Any]:
    return {"name": name, "description": "", "mode": None,
            "access_vlan": None, "native_vlan": None,
            "allowed_vlans": None, "ip": None, "mask": None,
            "shutdown": None}


def _mask_to_prefix(mask: str) -> int:
    return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen


def _prefix_to_mask(prefix: Union[int, str]) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{int(prefix)}").netmask)


def _norm_mask(token: str) -> str:
    """A second IP-address token may be a dotted mask or a prefix length."""
    token = token.strip()
    if token.isdigit():
        return _prefix_to_mask(token)
    return token


# ---- VLAN list parsing / formatting --------------------------------------
def _parse_comma_vlans(s: str) -> AllowedVlans:
    s = s.strip().lower()
    if s in ("all", "") or "add" == s:
        return "all" if s == "all" else None
    if s in ("none",):
        return []
    s = s.replace("add", "").strip()
    out: List[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return sorted(set(out))


def _parse_space_vlans(tokens: List[str]) -> AllowedVlans:
    """Huawei/HP style: '10 20 30 to 40' or 'all'."""
    joined = " ".join(tokens).strip().lower()
    if joined in ("all", ""):
        return "all" if joined == "all" else None
    out: List[int] = []
    i = 0
    toks = joined.split()
    while i < len(toks):
        t = toks[i]
        if t == "to" and out and i + 1 < len(toks) and toks[i + 1].isdigit():
            for v in range(out[-1] + 1, int(toks[i + 1]) + 1):
                out.append(v)
            i += 2
            continue
        if t.isdigit():
            out.append(int(t))
        i += 1
    return sorted(set(out))


def _compress(vlans: List[int]) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for v in sorted(set(vlans)):
        if ranges and v == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], v)
        else:
            ranges.append((v, v))
    return ranges


def _fmt_comma(allowed: AllowedVlans) -> str:
    if allowed == "all":
        return "all"
    if not allowed:
        return ""
    return ",".join(f"{a}-{b}" if a != b else str(a)
                    for a, b in _compress(allowed))


def _fmt_space(allowed: AllowedVlans) -> str:
    if allowed == "all":
        return "all"
    if not allowed:
        return ""
    return " ".join(f"{a} to {b}" if a != b else str(a)
                    for a, b in _compress(allowed))


# ===========================================================================
# Parsers  (config text -> model)
# ===========================================================================
def _blank_model() -> Dict[str, Any]:
    return {"hostname": "", "vlans": [], "interfaces": [], "unparsed": []}


def parse_cisco(text: str) -> Dict[str, Any]:
    """Also used for Arista EOS (same switchport CLI)."""
    m = _blank_model()
    cur_if: Optional[Dict[str, Any]] = None
    cur_vlan: Optional[Dict[str, Any]] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s or s == "!":
            continue
        low = s.lower()
        indented = line[:1] in (" ", "\t")

        if low.startswith("hostname "):
            m["hostname"] = s.split(None, 1)[1]
            cur_if = cur_vlan = None
            continue
        if re.match(r"interface\s+", low):
            cur_if = _new_iface(s.split(None, 1)[1])
            m["interfaces"].append(cur_if)
            cur_vlan = None
            continue
        if re.match(r"vlan\s+\d", low) and not indented:
            ids = _parse_comma_vlans(s.split(None, 1)[1])
            cur_vlan = None
            for vid in (ids if isinstance(ids, list) else []):
                cur_vlan = {"id": vid, "name": ""}
                m["vlans"].append(cur_vlan)
            cur_if = None
            continue

        if cur_vlan is not None and low.startswith("name "):
            cur_vlan["name"] = s.split(None, 1)[1]
            continue
        if cur_if is not None and indented:
            if low.startswith("description "):
                cur_if["description"] = s.split(None, 1)[1]
            elif low == "shutdown":
                cur_if["shutdown"] = True
            elif low == "no shutdown":
                cur_if["shutdown"] = False
            elif low == "switchport mode access":
                cur_if["mode"] = "access"
            elif low == "switchport mode trunk":
                cur_if["mode"] = "trunk"
            elif low.startswith("switchport access vlan "):
                cur_if["access_vlan"] = int(s.split()[-1])
                if not cur_if["mode"]:
                    cur_if["mode"] = "access"
            elif low.startswith("switchport trunk native vlan "):
                cur_if["native_vlan"] = int(s.split()[-1])
            elif low.startswith("switchport trunk allowed vlan "):
                cur_if["allowed_vlans"] = _parse_comma_vlans(
                    s[len("switchport trunk allowed vlan "):])
                cur_if["mode"] = cur_if["mode"] or "trunk"
            elif low.startswith("ip address "):
                _set_ip_cisco(cur_if, s)
            else:
                m["unparsed"].append(s)
            continue
        m["unparsed"].append(s)
    return m


def _set_ip_cisco(iface: Dict[str, Any], s: str):
    parts = s.split()
    # ip address A M  |  ip address A/len
    addr = parts[2]
    if "/" in addr:
        ip, pfx = addr.split("/", 1)
        iface["ip"], iface["mask"] = ip, _prefix_to_mask(pfx)
    elif len(parts) >= 4:
        iface["ip"], iface["mask"] = parts[2], _norm_mask(parts[3])


def parse_arista(text: str) -> Dict[str, Any]:
    return parse_cisco(text)


def parse_aruba(text: str) -> Dict[str, Any]:
    m = _blank_model()
    cur_if: Optional[Dict[str, Any]] = None
    cur_vlan: Optional[Dict[str, Any]] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s or s in ("!", "exit"):
            continue
        low = s.lower()
        indented = line[:1] in (" ", "\t")
        if low.startswith("hostname "):
            m["hostname"] = s.split(None, 1)[1]
            cur_if = cur_vlan = None
            continue
        if re.match(r"interface\s+", low):
            cur_if = _new_iface(s.split(None, 1)[1])
            m["interfaces"].append(cur_if)
            cur_vlan = None
            continue
        if re.match(r"vlan\s+\d", low) and not indented:
            ids = _parse_comma_vlans(s.split(None, 1)[1])
            cur_vlan = None
            for vid in (ids if isinstance(ids, list) else []):
                cur_vlan = {"id": vid, "name": ""}
                m["vlans"].append(cur_vlan)
            cur_if = None
            continue
        if cur_vlan is not None and low.startswith("name "):
            cur_vlan["name"] = s.split(None, 1)[1]
            continue
        if cur_if is not None and indented:
            if low.startswith("description "):
                cur_if["description"] = s.split(None, 1)[1]
            elif low == "shutdown":
                cur_if["shutdown"] = True
            elif low == "no shutdown":
                cur_if["shutdown"] = False
            elif low.startswith("vlan access "):
                cur_if["mode"] = "access"
                cur_if["access_vlan"] = int(s.split()[-1])
            elif low.startswith("vlan trunk native "):
                cur_if["mode"] = cur_if["mode"] or "trunk"
                cur_if["native_vlan"] = int(s.split()[-1])
            elif low.startswith("vlan trunk allowed "):
                cur_if["mode"] = "trunk"
                cur_if["allowed_vlans"] = _parse_comma_vlans(
                    s[len("vlan trunk allowed "):])
            elif low.startswith("ip address "):
                _set_ip_cisco(cur_if, s)
            else:
                m["unparsed"].append(s)
            continue
        m["unparsed"].append(s)
    return m


def _parse_huawei_like(text: str, access_kw: str, allow_kw: str) -> Dict[str, Any]:
    """Shared parser for Huawei VRP and HPE Comware (differ by keywords)."""
    m = _blank_model()
    cur_if: Optional[Dict[str, Any]] = None
    cur_vlan: Optional[Dict[str, Any]] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s or s in ("#", "quit", "return"):
            cur_if = cur_vlan = None if s in ("#",) else (cur_if or None)
            continue
        low = s.lower()
        indented = line[:1] in (" ", "\t")
        if low.startswith("sysname "):
            m["hostname"] = s.split(None, 1)[1]
            cur_if = cur_vlan = None
            continue
        if low.startswith("vlan batch "):
            for vid in (_parse_space_vlans(s.split()[2:]) or []):
                m["vlans"].append({"id": vid, "name": ""})
            continue
        if re.match(r"vlan\s+\d", low) and not indented:
            rest = s.split(None, 1)[1]
            if " to " in rest.lower():
                ids = _parse_space_vlans(rest.split())
                for vid in (ids if isinstance(ids, list) else []):
                    m["vlans"].append({"id": vid, "name": ""})
                cur_vlan = None
            else:
                cur_vlan = {"id": int(rest.split()[0]), "name": ""}
                m["vlans"].append(cur_vlan)
            cur_if = None
            continue
        if re.match(r"interface\s+", low):
            cur_if = _new_iface(s.split(None, 1)[1])
            m["interfaces"].append(cur_if)
            cur_vlan = None
            continue

        if cur_vlan is not None and low.startswith("name "):
            cur_vlan["name"] = s.split(None, 1)[1]
            continue
        if cur_if is not None:
            if low.startswith("description "):
                cur_if["description"] = s.split(None, 1)[1]
            elif low == "shutdown":
                cur_if["shutdown"] = True
            elif low == "undo shutdown":
                cur_if["shutdown"] = False
            elif low == "port link-type access":
                cur_if["mode"] = "access"
            elif low == "port link-type trunk":
                cur_if["mode"] = "trunk"
            elif low.startswith(access_kw):
                cur_if["mode"] = cur_if["mode"] or "access"
                cur_if["access_vlan"] = int(s.split()[-1])
            elif low.startswith("port trunk pvid vlan "):
                cur_if["native_vlan"] = int(s.split()[-1])
            elif low.startswith(allow_kw):
                cur_if["mode"] = "trunk"
                cur_if["allowed_vlans"] = _parse_space_vlans(
                    s[len(allow_kw):].split())
            elif low.startswith("ip address "):
                _set_ip_cisco(cur_if, s)
            else:
                m["unparsed"].append(s)
            continue
        m["unparsed"].append(s)
    return m


def parse_huawei(text: str) -> Dict[str, Any]:
    return _parse_huawei_like(text, "port default vlan ",
                              "port trunk allow-pass vlan ")


def parse_hp(text: str) -> Dict[str, Any]:
    return _parse_huawei_like(text, "port access vlan ",
                              "port trunk permit vlan ")


# ===========================================================================
# Generators  (model -> config text)
# ===========================================================================
def _gen_cisco(m: Dict[str, Any], arista: bool = False) -> List[str]:
    out: List[str] = []
    if m["hostname"]:
        out.append(f"hostname {m['hostname']}")
        out.append("!")
    for v in m["vlans"]:
        out.append(f"vlan {v['id']}")
        if v["name"]:
            out.append(f" name {v['name']}")
    if m["vlans"]:
        out.append("!")
    for i in m["interfaces"]:
        out.append(f"interface {i['name']}")
        if i["description"]:
            out.append(f" description {i['description']}")
        if i["ip"]:
            out.append(" no switchport")
            out.append(f" ip address {i['ip']} {i['mask']}")
        if i["mode"] == "access":
            out.append(" switchport mode access")
            if i["access_vlan"]:
                out.append(f" switchport access vlan {i['access_vlan']}")
        elif i["mode"] == "trunk":
            out.append(" switchport mode trunk")
            if i["native_vlan"]:
                out.append(f" switchport trunk native vlan {i['native_vlan']}")
            allowed = _fmt_comma(i["allowed_vlans"])
            if allowed:
                out.append(f" switchport trunk allowed vlan {allowed}")
        if i["shutdown"] is True:
            out.append(" shutdown")
        elif i["shutdown"] is False:
            out.append(" no shutdown")
        out.append("!")
    return out


def _gen_aruba(m: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if m["hostname"]:
        out.append(f"hostname {m['hostname']}")
    for v in m["vlans"]:
        out.append(f"vlan {v['id']}")
        if v["name"]:
            out.append(f"    name {v['name']}")
    for i in m["interfaces"]:
        out.append(f"interface {i['name']}")
        if i["description"]:
            out.append(f"    description {i['description']}")
        if i["shutdown"] is True:
            out.append("    shutdown")
        else:
            out.append("    no shutdown")
        if i["ip"]:
            out.append(f"    ip address {i['ip']}/{_mask_to_prefix(i['mask'])}")
        if i["mode"] == "access" and i["access_vlan"]:
            out.append(f"    vlan access {i['access_vlan']}")
        elif i["mode"] == "trunk":
            if i["native_vlan"]:
                out.append(f"    vlan trunk native {i['native_vlan']}")
            allowed = _fmt_comma(i["allowed_vlans"]) or "all"
            out.append(f"    vlan trunk allowed {allowed}")
    return out


def _gen_huawei_like(m: Dict[str, Any], access_tmpl: str,
                     allow_tmpl: str, svi_prefix: str) -> List[str]:
    out: List[str] = []
    if m["hostname"]:
        out.append(f"sysname {m['hostname']}")
    out.append("#")
    for v in m["vlans"]:
        out.append(f"vlan {v['id']}")
        if v["name"]:
            out.append(f" name {v['name']}")
        out.append("#")
    for i in m["interfaces"]:
        out.append(f"interface {i['name']}")
        if i["description"]:
            out.append(f" description {i['description']}")
        if i["mode"] == "access":
            out.append(" port link-type access")
            if i["access_vlan"]:
                out.append(access_tmpl.format(vlan=i["access_vlan"]))
        elif i["mode"] == "trunk":
            out.append(" port link-type trunk")
            if i["native_vlan"]:
                out.append(f" port trunk pvid vlan {i['native_vlan']}")
            allowed = _fmt_space(i["allowed_vlans"]) or "all"
            out.append(allow_tmpl.format(vlans=allowed))
        if i["ip"]:
            out.append(f" ip address {i['ip']} {i['mask']}")
        if i["shutdown"] is True:
            out.append(" shutdown")
        elif i["shutdown"] is False:
            out.append(" undo shutdown")
        out.append("#")
    return out


def _gen_huawei(m: Dict[str, Any]) -> List[str]:
    return _gen_huawei_like(m, " port default vlan {vlan}",
                            " port trunk allow-pass vlan {vlans}", "Vlanif")


def _gen_hp(m: Dict[str, Any]) -> List[str]:
    return _gen_huawei_like(m, " port access vlan {vlan}",
                            " port trunk permit vlan {vlans}", "Vlan-interface")


PARSERS = {"cisco": parse_cisco, "arista": parse_arista, "aruba": parse_aruba,
           "huawei": parse_huawei, "hp": parse_hp}
GENERATORS = {
    "cisco": lambda m: _gen_cisco(m, arista=False),
    "arista": lambda m: _gen_cisco(m, arista=True),
    "aruba": _gen_aruba,
    "huawei": _gen_huawei,
    "hp": _gen_hp,
}
COMMENT = {"cisco": "!", "arista": "!", "aruba": "!", "huawei": "#", "hp": "#"}


def convert(text: str, src: str, dst: str) -> Tuple[str, Dict[str, Any]]:
    """Return (converted_config, info) where info has counts and notes."""
    src, dst = src.lower(), dst.lower()
    if src not in PARSERS:
        raise ValueError(f"Unknown source vendor '{src}'")
    if dst not in GENERATORS:
        raise ValueError(f"Unknown target vendor '{dst}'")
    model = PARSERS[src](text)
    body = GENERATORS[dst](model)
    cm = COMMENT[dst]

    header = [
        f"{cm} ============================================================",
        f"{cm} Converted {VENDOR_LABELS[src]}  ->  {VENDOR_LABELS[dst]}",
        f"{cm} Common constructs only. REVIEW before applying - interface",
        f"{cm} names are kept as-is and may need adjusting per platform.",
        f"{cm} ============================================================",
    ]
    lines = header + [cm] + body

    if model["unparsed"]:
        lines.append(cm)
        lines.append(f"{cm} ---- {len(model['unparsed'])} line(s) not "
                     f"converted (left for manual review) ----")
        for u in model["unparsed"]:
            lines.append(f"{cm} {u}")

    info = {
        "hostname": model["hostname"],
        "vlans": len(model["vlans"]),
        "interfaces": len(model["interfaces"]),
        "unparsed": len(model["unparsed"]),
    }
    return "\n".join(lines) + "\n", info


def _cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Convert switch configs between vendor CLIs.")
    p.add_argument("--from", dest="src", required=True, choices=VENDORS)
    p.add_argument("--to", dest="dst", required=True, choices=VENDORS)
    p.add_argument("input", help="Path to the source config file.")
    p.add_argument("-o", "--output", help="Write result to this file.")
    args = p.parse_args(argv)
    if not os.path.isfile(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 2
    with open(args.input, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    result, info = convert(text, args.src, args.dst)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result)
        print(f"Wrote {args.output}  "
              f"(vlans={info['vlans']}, interfaces={info['interfaces']}, "
              f"unconverted={info['unparsed']})")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
