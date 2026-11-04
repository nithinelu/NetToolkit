#!/usr/bin/env python3
"""
FortiGate (FortiOS) configuration builder - core logic
======================================================

Turns a "spec" dict into copy-paste-ready FortiOS CLI, organised as a
Day-0 -> Day-1 -> Day-2/100 bring-up:

  Day 0  (system bring-up) : hostname, timezone, admin accounts + hardening,
                             password policy, DNS, NTP, interfaces, routing, DHCP
  Day 1  (deployment)      : address objects/groups, IP pools, VIPs
                             (port-forwards), firewall policies with NAT and
                             security profiles (AV/Web/IPS/App + SSL inspection)
  Day 2+ (operations)      : syslog, FortiAnalyzer, SNMP, HA, auto-updates

Generates text only - it never touches a device. Command syntax follows the
FortiOS 7.x CLI (see Fortinet admin/CLI guides); review before pasting, as a few
fields vary by model/version.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


# --------------------------------------------------------------- helpers
def q(val: str) -> str:
    return '"' + str(val).replace('"', '') + '"'


def qlist(val: str) -> str:
    """'HTTP, HTTPS ping' -> '"HTTP" "HTTPS" "ping"'."""
    parts = [p for p in str(val).replace(",", " ").split() if p]
    return " ".join(q(p) for p in parts) if parts else '"all"'


# --------------------------------------------------------------- Day 0
def gen_global(spec: Dict[str, Any]) -> List[str]:
    out = ["config system global", f"    set hostname {q(spec['hostname'])}"]
    if spec.get("timezone"):
        out.append(f"    set timezone {q(spec['timezone'])}")
    if spec.get("admin_timeout"):
        out.append(f"    set admintimeout {spec['admin_timeout']}")
    if spec.get("lockout_threshold"):
        out.append(f"    set admin-lockout-threshold {spec['lockout_threshold']}")
    if spec.get("lockout_duration"):
        out.append(f"    set admin-lockout-duration {spec['lockout_duration']}")
    if spec.get("admin_ssh_port"):
        out.append(f"    set admin-ssh-port {spec['admin_ssh_port']}")
    if spec.get("admin_https_port"):
        out.append(f"    set admin-sport {spec['admin_https_port']}")
    if spec.get("strong_crypto"):
        out.append("    set strong-crypto enable")
    out.append("end")
    return out


def gen_password_policy(spec: Dict[str, Any]) -> List[str]:
    if not spec.get("password_policy"):
        return []
    return [
        "config system password-policy",
        "    set status enable",
        "    set minimum-length 12",
        "    set min-lower-case-letter 1",
        "    set min-upper-case-letter 1",
        "    set min-number 1",
        "    set min-non-alphanumeric 1",
        "    set expire-status disable",
        "end",
    ]


def gen_admins(spec: Dict[str, Any]) -> List[str]:
    admins = spec.get("admins", [])
    if not admins:
        return []
    out = ["config system admin"]
    for a in admins:
        out.append(f"    edit {q(a['name'])}")
        out.append(f"        set accprofile {q(a.get('profile', 'super_admin'))}")
        if a.get("password"):
            out.append(f"        set password {q(a['password'])}")
        th = a.get("trusthost", "")
        if th:
            for i, host in enumerate(_split_hosts(th), start=1):
                out.append(f"        set trusthost{i} {host}")
        out.append("    next")
    out.append("end")
    return out


def _split_hosts(value: str) -> List[str]:
    """Accept 'a.b.c.d/24' or 'a.b.c.d m.m.m.m', comma/semicolon separated."""
    out = []
    for item in str(value).replace(";", ",").split(","):
        item = item.strip()
        if item:
            out.append(item)
    return out


def gen_dns(spec: Dict[str, Any]) -> List[str]:
    dns = spec.get("dns", {})
    if not dns.get("primary") and not dns.get("secondary"):
        return []
    out = ["config system dns"]
    if dns.get("primary"):
        out.append(f"    set primary {dns['primary']}")
    if dns.get("secondary"):
        out.append(f"    set secondary {dns['secondary']}")
    out.append("end")
    return out


def gen_ntp(spec: Dict[str, Any]) -> List[str]:
    servers = spec.get("ntp", [])
    if not servers:
        return []
    out = ["config system ntp", "    set ntpsync enable", "    set type custom",
           "    config ntpserver"]
    for i, s in enumerate(servers, start=1):
        out += [f"        edit {i}", f"            set server {q(s)}",
                "        next"]
    out += ["    end", "    set syncinterval 60", "end"]
    return out


def gen_interfaces(spec: Dict[str, Any]) -> List[str]:
    ifaces = spec.get("interfaces", [])
    if not ifaces:
        return []
    out = ["config system interface"]
    for i in ifaces:
        out.append(f"    edit {q(i['name'])}")
        if i.get("alias"):
            out.append(f"        set alias {q(i['alias'])}")
        if i.get("role"):
            out.append(f"        set role {i['role']}")
        mode = i.get("mode", "static")
        out.append(f"        set mode {mode}")
        if mode == "static" and i.get("ip"):
            out.append(f"        set ip {i['ip']} {i.get('mask', '255.255.255.0')}")
        if i.get("allowaccess"):
            out.append(f"        set allowaccess {i['allowaccess']}")
        if i.get("description"):
            out.append(f"        set description {q(i['description'])}")
        out.append("    next")
    out.append("end")
    return out


def gen_static_routes(spec: Dict[str, Any]) -> List[str]:
    routes = spec.get("static_routes", [])
    if not routes:
        return []
    out = ["config router static"]
    for seq, r in enumerate(routes, start=1):
        out.append(f"    edit {seq}")
        out.append(f"        set dst {r.get('dst', '0.0.0.0 0.0.0.0')}")
        if r.get("gateway"):
            out.append(f"        set gateway {r['gateway']}")
        if r.get("device"):
            out.append(f"        set device {q(r['device'])}")
        out.append("    next")
    out.append("end")
    return out


def gen_dhcp(spec: Dict[str, Any]) -> List[str]:
    servers = spec.get("dhcp", [])
    if not servers:
        return []
    out = ["config system dhcp server"]
    for sid, d in enumerate(servers, start=1):
        out.append(f"    edit {sid}")
        out.append(f"        set interface {q(d['interface'])}")
        if d.get("gateway"):
            out.append(f"        set default-gateway {d['gateway']}")
        if d.get("netmask"):
            out.append(f"        set netmask {d['netmask']}")
        if d.get("dns_server"):
            out.append("        set dns-service specify")
            out.append(f"        set dns-server1 {d['dns_server']}")
        else:
            out.append("        set dns-service default")
        if d.get("lease"):
            out.append(f"        set lease-time {d['lease']}")
        out.append("        config ip-range")
        out.append("            edit 1")
        out.append(f"                set start-ip {d['start']}")
        out.append(f"                set end-ip {d['end']}")
        out.append("            next")
        out.append("        end")
        out.append("    next")
    out.append("end")
    return out


# --------------------------------------------------------------- Day 1
def gen_addresses(spec: Dict[str, Any]) -> List[str]:
    addrs = spec.get("addresses", [])
    if not addrs:
        return []
    out = ["config firewall address"]
    for a in addrs:
        out.append(f"    edit {q(a['name'])}")
        t = a.get("type", "subnet")
        if t == "iprange":
            out.append("        set type iprange")
            lo, _, hi = str(a["value"]).partition("-")
            out.append(f"        set start-ip {lo.strip()}")
            out.append(f"        set end-ip {hi.strip()}")
        elif t == "fqdn":
            out.append("        set type fqdn")
            out.append(f"        set fqdn {q(a['value'])}")
        else:
            out.append(f"        set subnet {a['value']}")
        out.append("    next")
    out.append("end")
    return out


def gen_addrgrps(spec: Dict[str, Any]) -> List[str]:
    grps = spec.get("addrgrps", [])
    if not grps:
        return []
    out = ["config firewall addrgrp"]
    for g in grps:
        out.append(f"    edit {q(g['name'])}")
        out.append(f"        set member {qlist(g['members'])}")
        out.append("    next")
    out.append("end")
    return out


def gen_ippools(spec: Dict[str, Any]) -> List[str]:
    pools = spec.get("ippools", [])
    if not pools:
        return []
    out = ["config firewall ippool"]
    for p in pools:
        out.append(f"    edit {q(p['name'])}")
        out.append(f"        set type {p.get('type', 'overload')}")
        out.append(f"        set startip {p['startip']}")
        out.append(f"        set endip {p.get('endip', p['startip'])}")
        out.append("    next")
    out.append("end")
    return out


def gen_vips(spec: Dict[str, Any]) -> List[str]:
    vips = spec.get("vips", [])
    if not vips:
        return []
    out = ["config firewall vip"]
    for v in vips:
        out.append(f"    edit {q(v['name'])}")
        if v.get("extintf"):
            out.append(f"        set extintf {q(v['extintf'])}")
        out.append(f"        set extip {v['extip']}")
        out.append(f"        set mappedip {q(v['mappedip'])}")
        if v.get("extport") or v.get("mappedport"):
            out.append("        set portforward enable")
            out.append(f"        set protocol {v.get('protocol', 'tcp')}")
            if v.get("extport"):
                out.append(f"        set extport {v['extport']}")
            if v.get("mappedport"):
                out.append(f"        set mappedport {v['mappedport']}")
        out.append("    next")
    out.append("end")
    return out


SSL_PROFILES = {"none": "no-inspection",
                "certificate": "certificate-inspection",
                "deep": "deep-inspection"}


def gen_policies(spec: Dict[str, Any]) -> List[str]:
    policies = spec.get("policies", [])
    if not policies:
        return []
    out = ["config firewall policy"]
    for pid, p in enumerate(policies, start=1):
        out.append(f"    edit {pid}")
        if p.get("name"):
            out.append(f"        set name {q(p['name'])}")
        out.append(f"        set srcintf {qlist(p.get('srcintf', 'any'))}")
        out.append(f"        set dstintf {qlist(p.get('dstintf', 'any'))}")
        out.append(f"        set srcaddr {qlist(p.get('srcaddr', 'all'))}")
        out.append(f"        set dstaddr {qlist(p.get('dstaddr', 'all'))}")
        out.append(f"        set action {p.get('action', 'accept')}")
        out.append(f"        set schedule {q(p.get('schedule', 'always'))}")
        out.append(f"        set service {qlist(p.get('service', 'ALL'))}")
        profiles = p.get("profiles", {}) or {}
        if p.get("action", "accept") == "accept":
            if p.get("nat"):
                out.append("        set nat enable")
                if p.get("ippool"):
                    out.append("        set ippool enable")
                    out.append(f"        set poolname {qlist(p['ippool'])}")
            applied = []
            if profiles.get("av"):
                applied.append(("av-profile", "default"))
            if profiles.get("webfilter"):
                applied.append(("webfilter-profile", "default"))
            if profiles.get("ips"):
                applied.append(("ips-sensor", "default"))
            if profiles.get("appctrl"):
                applied.append(("application-list", "default"))
            if applied:
                out.append("        set utm-status enable")
                for key, val in applied:
                    out.append(f"        set {key} {q(val)}")
                ssl = SSL_PROFILES.get(profiles.get("ssl", "certificate"),
                                       "certificate-inspection")
                out.append(f"        set ssl-ssh-profile {q(ssl)}")
        out.append(f"        set logtraffic {p.get('log', 'all')}")
        out.append("    next")
    out.append("end")
    return out


# --------------------------------------------------------------- Day 2+
def gen_syslog(spec: Dict[str, Any]) -> List[str]:
    sl = spec.get("syslog", {})
    if not sl.get("server"):
        return []
    return [
        "config log syslogd setting",
        "    set status enable",
        f"    set server {q(sl['server'])}",
        f"    set port {sl.get('port', 514)}",
        f"    set mode {sl.get('mode', 'udp')}",
        f"    set facility {sl.get('facility', 'local7')}",
        "    set format default",
        "end",
    ]


def gen_fortianalyzer(spec: Dict[str, Any]) -> List[str]:
    faz = spec.get("fortianalyzer", {})
    if not faz.get("server"):
        return []
    return [
        "config log fortianalyzer setting",
        "    set status enable",
        f"    set server {q(faz['server'])}",
        "    set upload-option realtime",
        "end",
    ]


def gen_snmp(spec: Dict[str, Any]) -> List[str]:
    snmp = spec.get("snmp", {})
    if not snmp.get("enabled"):
        return []
    out = ["config system snmp sysinfo", "    set status enable"]
    if snmp.get("contact"):
        out.append(f"    set contact-info {q(snmp['contact'])}")
    if snmp.get("location"):
        out.append(f"    set location {q(snmp['location'])}")
    out.append("end")
    comms = snmp.get("communities", [])
    if comms:
        out.append("config system snmp community")
        for cid, c in enumerate(comms, start=1):
            out.append(f"    edit {cid}")
            out.append(f"        set name {q(c['name'])}")
            out.append("        set status enable")
            if c.get("hosts"):
                out.append("        config hosts")
                for hid, host in enumerate(_split_hosts(c["hosts"]), start=1):
                    out += [f"            edit {hid}",
                            f"                set ip {host}", "            next"]
                out.append("        end")
            out.append("        set query-v2c-status "
                       + ("enable" if c.get("queries", True) else "disable"))
            out.append("        set trap-v2c-status "
                       + ("enable" if c.get("traps", False) else "disable"))
            out.append("    next")
        out.append("end")
    return out


def gen_ha(spec: Dict[str, Any]) -> List[str]:
    ha = spec.get("ha", {})
    if not ha.get("enabled"):
        return []
    out = ["config system ha",
           f"    set group-name {q(ha.get('group_name', 'FGT-HA'))}",
           f"    set mode {ha.get('mode', 'a-p')}"]
    if ha.get("password"):
        out.append(f"    set password {q(ha['password'])}")
    out.append(f"    set hbdev {qlist(ha.get('hbdev', 'port3'))} 50")
    if ha.get("priority"):
        out.append(f"    set priority {ha['priority']}")
    out.append("    set override " + ("enable" if ha.get("override") else "disable"))
    if ha.get("mgmt_intf"):
        out.append("    set ha-mgmt-status enable")
        out.append("    config ha-mgmt-interfaces")
        out.append("        edit 1")
        out.append(f"            set interface {q(ha['mgmt_intf'])}")
        out.append("            set gateway " + (ha.get("mgmt_gw", "0.0.0.0")))
        out.append("        next")
        out.append("    end")
    out.append("end")
    return out


def gen_autoupdate(spec: Dict[str, Any]) -> List[str]:
    if not spec.get("autoupdate"):
        return []
    return [
        "config system autoupdate schedule",
        "    set status enable",
        "    set frequency automatic",
        "end",
    ]


SECTIONS = [
    ("DAY 0 - SYSTEM BRING-UP", [
        gen_global, gen_password_policy, gen_admins, gen_dns, gen_ntp,
        gen_interfaces, gen_static_routes, gen_dhcp]),
    ("DAY 1 - DEPLOYMENT (OBJECTS, NAT, POLICIES)", [
        gen_addresses, gen_addrgrps, gen_ippools, gen_vips, gen_policies]),
    ("DAY 2+ - OPERATIONS & HARDENING", [
        gen_syslog, gen_fortianalyzer, gen_snmp, gen_ha, gen_autoupdate]),
]


def build_config(spec: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# ==========================================================",
        f"# FortiGate configuration for {spec.get('hostname', 'FortiGate')}",
        f"# Generated by NetToolkit on {datetime.now():%Y-%m-%d %H:%M:%S}",
        "# FortiOS 7.x CLI. Review before pasting; a few fields vary by model.",
        "# Paste into the CLI console (or via 'config' in an SSH session).",
        "# ==========================================================",
    ]
    for title, gens in SECTIONS:
        block: List[str] = []
        for gen in gens:
            block.extend(gen(spec))
        if block:
            lines.append("")
            lines.append(f"# ---------- {title} ----------")
            lines.extend(block)
    lines.append("")
    lines.append("# Save is automatic on FortiOS (each 'end' commits).")
    return "\n".join(lines) + "\n"


EXAMPLE_SPEC: Dict[str, Any] = {
    "hostname": "FGT-EDGE-01", "timezone": "Asia/Muscat",
    "admin_timeout": 10, "lockout_threshold": 3, "lockout_duration": 300,
    "admin_ssh_port": 22, "strong_crypto": True, "password_policy": True,
    "dns": {"primary": "9.9.9.9", "secondary": "149.112.112.112"},
    "ntp": ["0.pool.ntp.org", "1.pool.ntp.org"],
    "admins": [{"name": "netadmin", "password": "ChangeMe_123!",
                "profile": "super_admin", "trusthost": "10.0.99.0/24"}],
    "interfaces": [
        {"name": "port1", "alias": "WAN", "role": "wan", "mode": "static",
         "ip": "203.0.113.2", "mask": "255.255.255.248",
         "allowaccess": "ping", "description": "ISP uplink"},
        {"name": "port2", "alias": "LAN", "role": "lan", "mode": "static",
         "ip": "10.0.10.1", "mask": "255.255.255.0",
         "allowaccess": "ping https ssh", "description": "Internal LAN"},
    ],
    "static_routes": [{"dst": "0.0.0.0 0.0.0.0", "gateway": "203.0.113.1",
                       "device": "port1"}],
    "dhcp": [{"interface": "port2", "gateway": "10.0.10.1",
              "netmask": "255.255.255.0", "start": "10.0.10.100",
              "end": "10.0.10.200", "dns_server": "10.0.10.1", "lease": 86400}],
    "addresses": [{"name": "LAN_NET", "type": "subnet",
                   "value": "10.0.10.0 255.255.255.0"},
                  {"name": "WebSrv", "type": "subnet",
                   "value": "10.0.10.50 255.255.255.255"}],
    "addrgrps": [],
    "ippools": [],
    "vips": [{"name": "VIP_HTTPS", "extintf": "port1", "extip": "203.0.113.2",
              "mappedip": "10.0.10.50", "protocol": "tcp", "extport": "443",
              "mappedport": "443"}],
    "policies": [
        {"name": "LAN_to_Internet", "srcintf": "port2", "dstintf": "port1",
         "srcaddr": "LAN_NET", "dstaddr": "all", "service": "ALL",
         "action": "accept", "nat": True, "log": "all",
         "profiles": {"av": True, "webfilter": True, "ips": True,
                      "appctrl": True, "ssl": "certificate"}},
        {"name": "Inet_to_Web", "srcintf": "port1", "dstintf": "port2",
         "srcaddr": "all", "dstaddr": "VIP_HTTPS", "service": "HTTPS",
         "action": "accept", "nat": False, "log": "all",
         "profiles": {"av": True, "ips": True, "ssl": "certificate"}},
    ],
    "syslog": {"server": "10.0.99.20", "port": 514, "mode": "udp",
               "facility": "local7"},
    "fortianalyzer": {"server": "10.0.99.25"},
    "snmp": {"enabled": True, "contact": "noc@example.com",
             "location": "DC1 Rack A",
             "communities": [{"name": "public", "hosts": "10.0.99.0/24",
                              "queries": True, "traps": True}]},
    "ha": {"enabled": False, "group_name": "FGT-HA", "mode": "a-p",
           "password": "", "hbdev": "port3", "priority": 128,
           "override": False},
    "autoupdate": True,
}


def save_output(config: str, hostname: str, path: Optional[str] = None) -> str:
    if path:
        out_path = path
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-._" else "_"
                       for c in (hostname or "fortigate"))
        out_path = os.path.join(OUTPUT_DIR,
                                f"{safe}_{datetime.now():%Y%m%d_%H%M%S}.conf")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(config)
    return out_path


def _cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Build FortiGate (FortiOS) configs.")
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
            print(f"Spec not found: {args.load}", file=sys.stderr)
            return 2
        with open(args.load, encoding="utf-8") as fh:
            spec = json.load(fh)
    else:
        print("Provide --load SPEC.json or --example SPEC.json", file=sys.stderr)
        return 2
    config = build_config(spec)
    print(config)
    if not args.no_save:
        print("Saved to:", save_output(config, spec.get("hostname", "fortigate"),
                                       args.output))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
