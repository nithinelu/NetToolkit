#!/usr/bin/env python3
"""
Cisco Config Builder - core logic
=================================

Turns a "spec" dict (collected by the GUI or the CLI wizard) into a clean,
copy-paste-ready Cisco IOS / IOS-XE configuration. Generates text only; it
never touches a device.

CLI::

    python config_builder.py                 # interactive wizard
    python config_builder.py --example s.json
    python config_builder.py --load s.json -o sw1.txt
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


# ---------------------------------------------------------------- input helpers
def ask(prompt: str, default: Optional[str] = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        val = input(f"{prompt}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if val:
            return val
        if not required:
            return ""
        print("  ! This value is required.")


def ask_yn(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        val = input(f"{prompt} ({d}): ").strip().lower()
        if not val:
            return default
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False
        print("  ! Please answer y or n.")


def ask_int(prompt: str, default: Optional[int] = None,
            lo: Optional[int] = None, hi: Optional[int] = None) -> int:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            n = int(raw)
        except ValueError:
            print("  ! Enter a whole number.")
            continue
        if lo is not None and n < lo:
            print(f"  ! Must be >= {lo}.")
            continue
        if hi is not None and n > hi:
            print(f"  ! Must be <= {hi}.")
            continue
        return n


def ask_choice(prompt: str, choices: List[str], default: str) -> str:
    opts = "/".join(c if c != default else c.upper() for c in choices)
    while True:
        val = input(f"{prompt} ({opts}): ").strip().lower()
        if not val:
            return default
        if val in choices:
            return val
        matches = [c for c in choices if c.startswith(val)]
        if len(matches) == 1:
            return matches[0]
        print(f"  ! Choose one of: {', '.join(choices)}")


def ask_ip(prompt: str, required: bool = True,
           default: Optional[str] = None) -> str:
    while True:
        val = ask(prompt, default=default, required=required)
        if not val:
            return ""
        if is_valid_ip(val):
            return val
        print("  ! That is not a valid IP address (e.g. 192.168.1.1).")


def is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def normalize_mask(value: str) -> str:
    val = value.strip()
    if val.startswith("/"):
        val = val[1:]
    if val.isdigit():
        prefix = int(val)
        if not 0 <= prefix <= 32:
            raise ValueError("prefix out of range")
        return str(ipaddress.ip_network(f"0.0.0.0/{prefix}").netmask)
    ipaddress.ip_network(f"0.0.0.0/{val}")
    return val


def ask_mask(prompt: str, default: str = "255.255.255.0") -> str:
    while True:
        val = ask(prompt, default=default)
        try:
            return normalize_mask(val)
        except ValueError:
            print("  ! Enter a mask like 255.255.255.0 or a prefix like /24.")


def mask_to_wildcard(mask: str) -> str:
    return ".".join(str(255 - int(o)) for o in mask.split("."))


# ---------------------------------------------------------------- generators
def gen_base(spec: Dict[str, Any]) -> List[str]:
    out = ["!", "! ---- System ----", f"hostname {spec['hostname']}"]
    if spec.get("domain"):
        out.append(f"ip domain-name {spec['domain']}")
    if spec.get("enable_secret"):
        out.append(f"enable secret {spec['enable_secret']}")
    services = spec.get("services", {})
    if services.get("password_encryption"):
        out.append("service password-encryption")
    if services.get("no_domain_lookup"):
        out.append("no ip domain-lookup")
    if spec.get("banner"):
        out.append(f"banner motd ^{spec['banner'].replace('^', '')}^")
    return out


def gen_users(spec: Dict[str, Any]) -> List[str]:
    users = spec.get("users", [])
    if not users:
        return []
    out = ["!", "! ---- Local users ----"]
    for u in users:
        priv = u.get("privilege")
        priv_part = f"privilege {priv} " if priv else ""
        out.append(f"username {u['username']} {priv_part}secret {u['password']}")
    return out


def gen_services(spec: Dict[str, Any]) -> List[str]:
    services = spec.get("services", {})
    out: List[str] = []
    dns, ntp, logging = (services.get("dns", []), services.get("ntp", []),
                         services.get("logging", []))
    if dns or ntp or logging:
        out += ["!", "! ---- Services ----"]
    if dns:
        out.append("ip name-server " + " ".join(dns))
    for s in ntp:
        out.append(f"ntp server {s}")
    for s in logging:
        out.append(f"logging host {s}")
    return out


def gen_ssh(spec: Dict[str, Any]) -> List[str]:
    ssh = spec.get("ssh", {})
    if not ssh.get("enable"):
        return []
    out = ["!", "! ---- SSH ----"]
    if not spec.get("domain"):
        out.append("ip domain-name local.lan")
    out.append(f"crypto key generate rsa modulus {ssh.get('modulus', 2048)}")
    out.append(f"ip ssh version {ssh.get('version', 2)}")
    return out


def gen_snmp(spec: Dict[str, Any]) -> List[str]:
    snmp = spec.get("snmp")
    if not snmp:
        return []
    out = ["!", "! ---- SNMP ----"]
    for c in snmp.get("communities", []):
        out.append(f"snmp-server community {c['community']} "
                   f"{c.get('mode', 'ro').upper()}")
    if snmp.get("location"):
        out.append(f"snmp-server location {snmp['location']}")
    if snmp.get("contact"):
        out.append(f"snmp-server contact {snmp['contact']}")
    for h in snmp.get("trap_hosts", []):
        out.append(f"snmp-server host {h['host']} {h.get('community', 'public')}")
    return out


def gen_vlans(spec: Dict[str, Any]) -> List[str]:
    vlans = spec.get("vlans", [])
    if not vlans:
        return []
    out = ["!", "! ---- VLANs ----"]
    for v in vlans:
        out.append(f"vlan {v['id']}")
        if v.get("name"):
            out.append(f" name {v['name']}")
    return out


def _pc_body(ec: Dict[str, Any]) -> List[str]:
    body: List[str] = []
    kind = ec.get("type", "trunk")
    if kind == "access":
        body.append(" switchport mode access")
        if ec.get("vlan"):
            body.append(f" switchport access vlan {ec['vlan']}")
    elif kind == "trunk":
        if ec.get("encapsulation_dot1q"):
            body.append(" switchport trunk encapsulation dot1q")
        body.append(" switchport mode trunk")
        if ec.get("native"):
            body.append(f" switchport trunk native vlan {ec['native']}")
        if ec.get("allowed"):
            body.append(f" switchport trunk allowed vlan {ec['allowed']}")
    return body


def gen_etherchannel(spec: Dict[str, Any]) -> List[str]:
    bundles = spec.get("etherchannels", [])
    if not bundles:
        return []
    out = ["!", "! ---- EtherChannel (port-channels) ----"]
    for ec in bundles:
        kw = "range " if "-" in ec["members"] or "," in ec["members"] else ""
        out.append(f"interface {kw}{ec['members']}")
        if ec.get("type") in ("access", "trunk"):
            out.extend(_pc_body(ec))
        out.append(f" channel-group {ec['id']} mode {ec.get('mode', 'active')}")
        out.append(" no shutdown")
        out.append(f"interface port-channel {ec['id']}")
        if ec.get("description"):
            out.append(f" description {ec['description']}")
        if ec.get("type") == "l3":
            out.append(" no switchport")
            if ec.get("ip"):
                out.append(f" ip address {ec['ip']} {ec['mask']}")
        else:
            out.extend(_pc_body(ec))
        out.append(" no shutdown")
    return out


def gen_management(spec: Dict[str, Any]) -> List[str]:
    mgmt = spec.get("management")
    if not mgmt:
        return []
    out = ["!", "! ---- Management ----"]
    if spec.get("role") == "switch":
        out.append(f"interface vlan {mgmt['vlan']}")
        out.append(f" ip address {mgmt['ip']} {mgmt['mask']}")
        out.append(" no shutdown")
        if mgmt.get("gateway"):
            out.append(f"ip default-gateway {mgmt['gateway']}")
    else:
        out.append(f"interface {mgmt['interface']}")
        out.append(f" ip address {mgmt['ip']} {mgmt['mask']}")
        out.append(" no shutdown")
    return out


def gen_access_ports(spec: Dict[str, Any]) -> List[str]:
    ports = spec.get("access_ports", [])
    if not ports:
        return []
    out = ["!", "! ---- Access ports ----"]
    for p in ports:
        kw = "range " if "-" in p["interface"] or "," in p["interface"] else ""
        out.append(f"interface {kw}{p['interface']}")
        if p.get("description"):
            out.append(f" description {p['description']}")
        out.append(" switchport mode access")
        out.append(f" switchport access vlan {p['vlan']}")
        if p.get("voice_vlan"):
            out.append(f" switchport voice vlan {p['voice_vlan']}")
        if p.get("portfast", True):
            out.append(" spanning-tree portfast")
        if p.get("bpduguard", True):
            out.append(" spanning-tree bpduguard enable")
        out.append(" no shutdown")
    return out


def gen_trunk_ports(spec: Dict[str, Any]) -> List[str]:
    ports = spec.get("trunk_ports", [])
    if not ports:
        return []
    out = ["!", "! ---- Trunk ports ----"]
    for p in ports:
        kw = "range " if "-" in p["interface"] or "," in p["interface"] else ""
        out.append(f"interface {kw}{p['interface']}")
        if p.get("description"):
            out.append(f" description {p['description']}")
        if p.get("encapsulation_dot1q"):
            out.append(" switchport trunk encapsulation dot1q")
        out.append(" switchport mode trunk")
        if p.get("native"):
            out.append(f" switchport trunk native vlan {p['native']}")
        if p.get("allowed"):
            out.append(f" switchport trunk allowed vlan {p['allowed']}")
        out.append(" no shutdown")
    return out


def gen_l3_interfaces(spec: Dict[str, Any]) -> List[str]:
    ifaces = spec.get("l3_interfaces", [])
    if not ifaces:
        return []
    out = ["!", "! ---- Routed interfaces ----"]
    for i in ifaces:
        out.append(f"interface {i['interface']}")
        if i.get("description"):
            out.append(f" description {i['description']}")
        if spec.get("role") == "switch":
            out.append(" no switchport")
        out.append(f" ip address {i['ip']} {i['mask']}")
        out.append(" no shutdown")
    return out


def gen_hsrp(spec: Dict[str, Any]) -> List[str]:
    groups = spec.get("hsrp", [])
    if not groups:
        return []
    out = ["!", "! ---- First-hop redundancy (HSRP/VRRP) ----"]
    for g in groups:
        out.append(f"interface {g['interface']}")
        proto = g.get("protocol", "hsrp")
        grp = g.get("group", 1)
        if proto == "vrrp":
            out.append(f" vrrp {grp} ip {g['vip']}")
            if g.get("priority"):
                out.append(f" vrrp {grp} priority {g['priority']}")
            if g.get("preempt", True):
                out.append(f" vrrp {grp} preempt")
        else:
            if g.get("version"):
                out.append(f" standby version {g['version']}")
            out.append(f" standby {grp} ip {g['vip']}")
            if g.get("priority"):
                out.append(f" standby {grp} priority {g['priority']}")
            if g.get("preempt", True):
                out.append(f" standby {grp} preempt")
    return out


def gen_dhcp(spec: Dict[str, Any]) -> List[str]:
    dhcp = spec.get("dhcp")
    if not dhcp:
        return []
    pools, excluded = dhcp.get("pools", []), dhcp.get("excluded", [])
    if not pools and not excluded:
        return []
    out = ["!", "! ---- DHCP ----"]
    for rng in excluded:
        out.append(f"ip dhcp excluded-address {rng}")
    for p in pools:
        out.append(f"ip dhcp pool {p['name']}")
        out.append(f" network {p['network']} {p['mask']}")
        if p.get("gateway"):
            out.append(f" default-router {p['gateway']}")
        if p.get("dns"):
            out.append(" dns-server " + " ".join(p["dns"]))
        if p.get("domain"):
            out.append(f" domain-name {p['domain']}")
        if p.get("lease"):
            out.append(f" lease {p['lease']}")
    return out


def gen_acls(spec: Dict[str, Any]) -> List[str]:
    acls = spec.get("acls", [])
    if not acls:
        return []
    out = ["!", "! ---- Access lists ----"]
    for a in acls:
        out.append(f"ip access-list {a.get('type', 'extended')} {a['name']}")
        for entry in a.get("entries", []):
            out.append(f" {entry}")
        if a.get("apply_interface"):
            out.append(f"interface {a['apply_interface']}")
            out.append(f" ip access-group {a['name']} {a.get('direction', 'in')}")
        if a.get("apply_vty"):
            out.append("line vty 0 4")
            out.append(f" access-class {a['name']} in")
    return out


def gen_static_routes(spec: Dict[str, Any]) -> List[str]:
    routes = spec.get("static_routes", [])
    if not routes:
        return []
    out = ["!", "! ---- Static routes ----"]
    for r in routes:
        out.append(f"ip route {r['network']} {r['mask']} {r['next_hop']}")
    return out


def gen_ospf(spec: Dict[str, Any]) -> List[str]:
    ospf = spec.get("ospf")
    if not ospf:
        return []
    out = ["!", "! ---- OSPF ----", f"router ospf {ospf['process']}"]
    if ospf.get("router_id"):
        out.append(f" router-id {ospf['router_id']}")
    for n in ospf.get("networks", []):
        out.append(f" network {n['network']} {n['wildcard']} area {n['area']}")
    return out


def gen_lines(spec: Dict[str, Any]) -> List[str]:
    out = ["!", "! ---- Console / VTY lines ----"]
    has_users = bool(spec.get("users"))
    ssh_on = spec.get("ssh", {}).get("enable")
    telnet_on = spec.get("telnet")
    vty = spec.get("vty", {})
    timeout = vty.get("exec_timeout", "10 0")
    out.append("line con 0")
    out.append(f" exec-timeout {timeout}")
    if has_users:
        out.append(" login local")
    elif vty.get("console_password"):
        out.append(f" password {vty['console_password']}")
        out.append(" login")
    out.append(" logging synchronous")
    out.append("line vty 0 4")
    out.append(f" exec-timeout {timeout}")
    if has_users:
        out.append(" login local")
    elif vty.get("password"):
        out.append(f" password {vty['password']}")
        out.append(" login")
    transports = []
    if ssh_on:
        transports.append("ssh")
    if telnet_on:
        transports.append("telnet")
    if transports:
        out.append(" transport input " + " ".join(transports))
    return out


SECTION_ORDER = [
    gen_base, gen_users, gen_services, gen_ssh, gen_snmp, gen_vlans,
    gen_etherchannel, gen_management, gen_access_ports, gen_trunk_ports,
    gen_l3_interfaces, gen_hsrp, gen_dhcp, gen_acls,
    gen_static_routes, gen_ospf, gen_lines,
]


def build_config(spec: Dict[str, Any]) -> str:
    role = spec.get("role", "switch")
    lines: List[str] = [
        "! ==========================================================",
        f"! Configuration for {spec.get('hostname', 'device')} ({role})",
        f"! Generated by Cisco Config Builder on {datetime.now():%Y-%m-%d %H:%M:%S}",
        "! Review before pasting. Enter global config mode first:",
        "!   enable",
        "!   configure terminal",
        "! ==========================================================",
    ]
    for gen in SECTION_ORDER:
        lines.extend(gen(spec))
    lines += ["!", "end", "!",
              "! Remember to save:  write memory   (or  copy run start)"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- wizard
def _collect_ips(label: str) -> List[str]:
    ips: List[str] = []
    while True:
        ip = ask_ip(f"  {label} (blank to finish)", required=False)
        if not ip:
            break
        ips.append(ip)
    return ips


def wizard() -> Dict[str, Any]:
    print("\n=== Cisco Config Builder ===")
    print("Answer the prompts. Press Enter to accept [defaults] or skip "
          "optional items.\n")
    spec: Dict[str, Any] = {}
    spec["role"] = ask_choice("Device type", ["switch", "router"], "switch")
    is_switch = spec["role"] == "switch"

    print("\n-- System --")
    spec["hostname"] = ask("Hostname", required=True)
    spec["domain"] = ask("Domain name (optional)")
    spec["enable_secret"] = ask("Enable secret (optional)")
    spec["banner"] = ask("Login banner text (optional)")
    spec["services"] = {
        "password_encryption": ask_yn("Enable 'service password-encryption'?", True),
        "no_domain_lookup": ask_yn("Disable DNS lookups on typos "
                                   "('no ip domain-lookup')?", True),
        "dns": [], "ntp": [], "logging": [],
    }

    print("\n-- Local users --")
    spec["users"] = []
    if ask_yn("Add a local login user?", True):
        while True:
            u = {"username": ask("  Username", required=True),
                 "password": ask("  Password", required=True)}
            if ask_yn("  Full privilege (level 15)?", True):
                u["privilege"] = 15
            spec["users"].append(u)
            if not ask_yn("Add another user?", False):
                break

    print("\n-- Remote access --")
    ssh_on = ask_yn("Enable SSH (recommended)?", True)
    spec["ssh"] = {"enable": ssh_on}
    if ssh_on:
        spec["ssh"]["version"] = 2
        spec["ssh"]["modulus"] = ask_int("  RSA key modulus", 2048, lo=512, hi=4096)
    spec["telnet"] = ask_yn("Enable Telnet (insecure)?", False)
    spec["vty"] = {"exec_timeout": "10 0"}
    if not spec["users"]:
        pw = ask("  VTY line password (since no users defined)")
        if pw:
            spec["vty"]["password"] = pw

    print("\n-- Management IP --")
    if ask_yn("Configure a management IP?", True):
        if is_switch:
            spec["management"] = {
                "vlan": ask_int("  Management VLAN", 1, lo=1, hi=4094),
                "ip": ask_ip("  Management IP"),
                "mask": ask_mask("  Subnet mask"),
                "gateway": ask_ip("  Default gateway (optional)", required=False)}
        else:
            spec["management"] = {
                "interface": ask("  Interface (e.g. GigabitEthernet0/0)",
                                 required=True),
                "ip": ask_ip("  IP address"), "mask": ask_mask("  Subnet mask")}

    if is_switch:
        print("\n-- VLANs --")
        spec["vlans"] = []
        if ask_yn("Create VLANs?", True):
            while True:
                vid = ask_int("  VLAN ID", lo=1, hi=4094)
                name = ask("  VLAN name (optional)")
                spec["vlans"].append({"id": vid, "name": name})
                if not ask_yn("Add another VLAN?", True):
                    break

    print("\n-- Interfaces --")
    if is_switch:
        spec["access_ports"] = []
        if ask_yn("Configure access ports?", True):
            while True:
                p = {"interface": ask("  Interface or range "
                                      "(e.g. Gi1/0/1 or Gi1/0/1-12)",
                                      required=True),
                     "vlan": ask_int("  Access VLAN", 1, lo=1, hi=4094),
                     "description": ask("  Description (optional)")}
                vv = ask_int("  Voice VLAN (0 = none)", 0, lo=0, hi=4094)
                if vv:
                    p["voice_vlan"] = vv
                p["portfast"] = ask_yn("  Enable PortFast?", True)
                p["bpduguard"] = ask_yn("  Enable BPDU guard?", True)
                spec["access_ports"].append(p)
                if not ask_yn("Add another access port/range?", False):
                    break
        spec["trunk_ports"] = []
        if ask_yn("Configure trunk ports?", False):
            dot1q = ask_yn("  Need 'switchport trunk encapsulation dot1q'? "
                           "(older 3560/3750)", False)
            while True:
                p = {"interface": ask("  Interface or range", required=True),
                     "description": ask("  Description (optional)"),
                     "encapsulation_dot1q": dot1q}
                native = ask_int("  Native VLAN (0 = default)", 0, lo=0, hi=4094)
                if native:
                    p["native"] = native
                allowed = ask("  Allowed VLANs (e.g. 10,20,30, blank = all)")
                if allowed:
                    p["allowed"] = allowed
                spec["trunk_ports"].append(p)
                if not ask_yn("Add another trunk port/range?", False):
                    break

    spec["l3_interfaces"] = []
    if ask_yn("Configure routed (L3) interfaces?", not is_switch):
        while True:
            i = {"interface": ask("  Interface (e.g. GigabitEthernet0/1)",
                                  required=True),
                 "description": ask("  Description (optional)"),
                 "ip": ask_ip("  IP address"), "mask": ask_mask("  Subnet mask")}
            spec["l3_interfaces"].append(i)
            if not ask_yn("Add another routed interface?", False):
                break

    print("\n-- Routing --")
    spec["static_routes"] = []
    if ask_yn("Add a default route (0.0.0.0/0)?", not is_switch):
        nh = ask_ip("  Next-hop / gateway IP")
        spec["static_routes"].append({"network": "0.0.0.0", "mask": "0.0.0.0",
                                      "next_hop": nh})
    if ask_yn("Add other static routes?", False):
        while True:
            r = {"network": ask_ip("  Destination network"),
                 "mask": ask_mask("  Network mask"),
                 "next_hop": ask_ip("  Next-hop IP")}
            spec["static_routes"].append(r)
            if not ask_yn("Add another static route?", False):
                break
    if ask_yn("Configure OSPF?", False):
        ospf = {"process": ask_int("  OSPF process id", 1, lo=1, hi=65535),
                "router_id": ask_ip("  Router-id (optional)", required=False),
                "networks": []}
        print("  Add networks to advertise (blank network to finish):")
        while True:
            net = ask_ip("    Network (blank to finish)", required=False)
            if not net:
                break
            mask = ask_mask("    Network mask")
            area = ask("    Area", default="0")
            ospf["networks"].append({"network": net,
                                     "wildcard": mask_to_wildcard(mask),
                                     "area": area})
        spec["ospf"] = ospf

    print("\n-- Extra services (optional) --")
    if ask_yn("Add DNS name-servers?", False):
        spec["services"]["dns"] = _collect_ips("DNS server")
    if ask_yn("Add NTP servers?", False):
        spec["services"]["ntp"] = _collect_ips("NTP server")
    if ask_yn("Add a syslog/logging host?", False):
        spec["services"]["logging"] = _collect_ips("Logging host")

    print("\n-- EtherChannel --")
    spec["etherchannels"] = []
    if ask_yn("Configure an EtherChannel / port-channel?", False):
        while True:
            ec: Dict[str, Any] = {
                "id": ask_int("  Port-channel number", 1, lo=1, hi=128),
                "members": ask("  Member interfaces (e.g. Gi1/0/1-2)",
                               required=True),
                "mode": ask_choice("  Mode", ["active", "passive", "on",
                                              "desirable", "auto"], "active"),
                "description": ask("  Description (optional)")}
            ec["type"] = ask_choice("  Type", ["trunk", "access", "l3"], "trunk")
            if ec["type"] == "access":
                ec["vlan"] = ask_int("  Access VLAN", 1, lo=1, hi=4094)
            elif ec["type"] == "trunk":
                native = ask_int("  Native VLAN (0 = default)", 0, lo=0, hi=4094)
                if native:
                    ec["native"] = native
                allowed = ask("  Allowed VLANs (blank = all)")
                if allowed:
                    ec["allowed"] = allowed
            else:
                ec["ip"] = ask_ip("  IP address")
                ec["mask"] = ask_mask("  Subnet mask")
            spec["etherchannels"].append(ec)
            if not ask_yn("Add another port-channel?", False):
                break

    print("\n-- First-hop redundancy (HSRP/VRRP) --")
    spec["hsrp"] = []
    if ask_yn("Configure HSRP/VRRP (virtual gateway)?", False):
        while True:
            g: Dict[str, Any] = {
                "protocol": ask_choice("  Protocol", ["hsrp", "vrrp"], "hsrp"),
                "interface": ask("  Interface (e.g. Vlan10)", required=True),
                "group": ask_int("  Group number", 1, lo=0, hi=255),
                "vip": ask_ip("  Virtual IP (the gateway address)")}
            pri = ask_int("  Priority (0 = default 100)", 0, lo=0, hi=255)
            if pri:
                g["priority"] = pri
            g["preempt"] = ask_yn("  Enable preempt?", True)
            if g["protocol"] == "hsrp" and ask_yn("  Use HSRP version 2?", True):
                g["version"] = 2
            spec["hsrp"].append(g)
            if not ask_yn("Add another HSRP/VRRP group?", False):
                break

    print("\n-- DHCP server --")
    if ask_yn("Configure DHCP pools?", False):
        dhcp: Dict[str, Any] = {"excluded": [], "pools": []}
        print("  Excluded ranges (blank to finish):")
        while True:
            lo_ip = ask_ip("    First excluded IP (blank to finish)",
                           required=False)
            if not lo_ip:
                break
            hi_ip = ask_ip("    Last excluded IP (blank = just one)",
                           required=False)
            dhcp["excluded"].append(f"{lo_ip} {hi_ip}".strip())
        while True:
            p: Dict[str, Any] = {
                "name": ask("    Pool name", required=True),
                "network": ask_ip("    Network address"),
                "mask": ask_mask("    Subnet mask"),
                "gateway": ask_ip("    Default gateway (optional)",
                                  required=False)}
            dns = _collect_ips("    DNS server (blank to finish)")
            if dns:
                p["dns"] = dns
            dom = ask("    Domain name (optional)")
            if dom:
                p["domain"] = dom
            lease = ask("    Lease 'days hours minutes' (optional)")
            if lease:
                p["lease"] = lease
            dhcp["pools"].append(p)
            if not ask_yn("Add another DHCP pool?", False):
                break
        spec["dhcp"] = dhcp

    print("\n-- Access lists --")
    spec["acls"] = []
    if ask_yn("Configure an ACL?", False):
        while True:
            a: Dict[str, Any] = {
                "name": ask("  ACL name or number", required=True),
                "type": ask_choice("  Type", ["extended", "standard"],
                                   "extended"),
                "entries": []}
            print("  Enter ACL entries one per line; blank to finish:")
            while True:
                e = ask("    entry")
                if not e:
                    break
                a["entries"].append(e)
            if ask_yn("  Apply this ACL to an interface?", False):
                a["apply_interface"] = ask("    Interface", required=True)
                a["direction"] = ask_choice("    Direction", ["in", "out"], "in")
            if ask_yn("  Apply this ACL to VTY?", False):
                a["apply_vty"] = True
            spec["acls"].append(a)
            if not ask_yn("Add another ACL?", False):
                break

    print("\n-- SNMP --")
    if ask_yn("Configure SNMP?", False):
        snmp: Dict[str, Any] = {"communities": [], "trap_hosts": []}
        while True:
            snmp["communities"].append({
                "community": ask("  Community string", required=True),
                "mode": ask_choice("  Access", ["ro", "rw"], "ro")})
            if not ask_yn("  Add another community?", False):
                break
        snmp["location"] = ask("  Location (optional)")
        snmp["contact"] = ask("  Contact (optional)")
        if ask_yn("  Add SNMP trap host(s)?", False):
            while True:
                snmp["trap_hosts"].append({
                    "host": ask_ip("    Trap host IP"),
                    "community": ask("    Community", required=True)})
                if not ask_yn("  Add another trap host?", False):
                    break
        spec["snmp"] = snmp

    return spec


EXAMPLE_SPEC: Dict[str, Any] = {
    "role": "switch", "hostname": "ACCESS-SW1", "domain": "example.lan",
    "enable_secret": "Str0ngEnable!", "banner": "Authorized access only.",
    "services": {"password_encryption": True, "no_domain_lookup": True,
                 "dns": ["8.8.8.8"], "ntp": ["192.168.1.10"],
                 "logging": ["192.168.1.20"]},
    "users": [{"username": "admin", "password": "Adm1nP@ss", "privilege": 15}],
    "ssh": {"enable": True, "version": 2, "modulus": 2048}, "telnet": False,
    "vty": {"exec_timeout": "10 0"},
    "management": {"vlan": 99, "ip": "192.168.99.2", "mask": "255.255.255.0",
                   "gateway": "192.168.99.1"},
    "vlans": [{"id": 10, "name": "USERS"}, {"id": 20, "name": "VOICE"},
              {"id": 99, "name": "MGMT"}],
    "access_ports": [{"interface": "GigabitEthernet1/0/1-12", "vlan": 10,
                      "description": "User ports", "voice_vlan": 20,
                      "portfast": True, "bpduguard": True}],
    "trunk_ports": [{"interface": "GigabitEthernet1/0/24", "description": "Uplink",
                     "native": 99, "allowed": "10,20,99",
                     "encapsulation_dot1q": False}],
    "l3_interfaces": [],
    "etherchannels": [{"id": 1, "members": "GigabitEthernet1/0/47-48",
                       "mode": "active", "type": "trunk", "native": 99,
                       "allowed": "10,20,99", "description": "Uplink to core",
                       "encapsulation_dot1q": False}],
    "hsrp": [{"protocol": "hsrp", "interface": "Vlan10", "group": 10,
              "vip": "192.168.10.1", "priority": 110, "preempt": True,
              "version": 2}],
    "dhcp": {"excluded": ["192.168.10.1 192.168.10.10"],
             "pools": [{"name": "USERS", "network": "192.168.10.0",
                        "mask": "255.255.255.0", "gateway": "192.168.10.1",
                        "dns": ["8.8.8.8", "1.1.1.1"], "domain": "example.lan",
                        "lease": "0 12 0"}]},
    "acls": [{"name": "MGMT-ACCESS", "type": "standard",
              "entries": ["permit 192.168.99.0 0.0.0.255", "deny any log"],
              "apply_vty": True}],
    "snmp": {"communities": [{"community": "public", "mode": "ro"}],
             "location": "Wiring closet A", "contact": "noc@example.lan",
             "trap_hosts": [{"host": "192.168.99.20", "community": "public"}]},
    "static_routes": [{"network": "0.0.0.0", "mask": "0.0.0.0",
                       "next_hop": "192.168.99.1"}],
}


def save_output(config: str, hostname: str, path: Optional[str] = None) -> str:
    if path:
        out_path = path
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-._" else "_"
                       for c in (hostname or "device"))
        out_path = os.path.join(OUTPUT_DIR,
                                f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(config)
    return out_path


def _cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Build copy-paste Cisco configs.")
    p.add_argument("--load", metavar="SPEC.json")
    p.add_argument("--example", metavar="SPEC.json")
    p.add_argument("-o", "--output", metavar="FILE")
    p.add_argument("--no-save", action="store_true")
    args = p.parse_args(argv)

    if args.example:
        with open(args.example, "w", encoding="utf-8") as fh:
            json.dump(EXAMPLE_SPEC, fh, indent=2)
        print(f"Example spec written to {args.example}")
        return 0
    if args.load:
        if not os.path.isfile(args.load):
            print(f"Spec file not found: {args.load}", file=sys.stderr)
            return 2
        with open(args.load, encoding="utf-8") as fh:
            spec = json.load(fh)
    else:
        try:
            spec = wizard()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 1
    config = build_config(spec)
    print("\n" + "=" * 60)
    print("Generated configuration (copy/paste below):")
    print("=" * 60)
    print(config)
    if not args.no_save:
        out_path = save_output(config, spec.get("hostname", "device"),
                               args.output)
        print(f"Saved to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
