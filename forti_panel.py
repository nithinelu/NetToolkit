#!/usr/bin/env python3
"""FortiGate tab for NetToolkit - embeddable ttk.Frame.

Builds FortiOS CLI (Day 0 -> Day 100) via forti_builder, reusing the Config
Builder's list-editor / form-dialog widgets.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict

import forti_builder as fb
import theme
from config_panel import F, ListEditor


class FortiPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.vars: Dict[str, tk.Variable] = {}
        self.editors: Dict[str, ListEditor] = {}
        self._build()

    # -- helpers -----------------------------------------------------------
    def _v(self, key, default=""):
        self.vars[key] = tk.StringVar(value=str(default))
        return self.vars[key]

    def _b(self, key, default=False):
        self.vars[key] = tk.BooleanVar(value=default)
        return self.vars[key]

    def _row(self, parent, label, widget, r, c=0):
        ttk.Label(parent, text=label).grid(row=r, column=c, sticky="w",
                                           padx=(0, 8), pady=2)
        widget.grid(row=r, column=c + 1, sticky="ew", pady=2)

    # -- UI ----------------------------------------------------------------
    def _build(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Generate config", style="Accent.TButton",
                   command=self.generate).pack(side="left")
        ttk.Button(bar, text="Copy", command=self.copy).pack(side="left", padx=4)
        ttk.Button(bar, text="Save config...",
                   command=self.save_config).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Load spec...",
                   command=self.load_spec).pack(side="left")
        ttk.Button(bar, text="Save spec...",
                   command=self.save_spec).pack(side="left", padx=4)
        ttk.Button(bar, text="Load example",
                   command=lambda: self.populate(fb.EXAMPLE_SPEC)).pack(
            side="left", padx=4)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._tab_day0(nb)
        self._tab_day1(nb)
        self._tab_day2(nb)

        out = ttk.LabelFrame(self, text="Generated FortiOS CLI", padding=6)
        out.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.output = tk.Text(out, height=9, wrap="none",
                              background=theme.CONSOLE_BG,
                              foreground=theme.CONSOLE_FG, font=theme.MONO_FONT,
                              relief="flat", borderwidth=0, padx=8, pady=6)
        self.output.pack(fill="both", expand=True)

    def _tab_day0(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="Day 0 — System")
        g = ttk.LabelFrame(t, text="System & hardening", padding=8)
        g.pack(fill="x", pady=3)
        g.columnconfigure(1, weight=1)
        g.columnconfigure(3, weight=1)
        r = 0
        self._row(g, "Hostname", ttk.Entry(g, textvariable=self._v("hostname")), r)
        self._row(g, "Timezone", ttk.Entry(g, textvariable=self._v("timezone")),
                  r, 2); r += 1
        self._row(g, "Admin timeout (min)",
                  ttk.Entry(g, textvariable=self._v("admin_timeout", "10"),
                            width=8), r)
        self._row(g, "SSH port",
                  ttk.Entry(g, textvariable=self._v("admin_ssh_port", "22"),
                            width=8), r, 2); r += 1
        self._row(g, "Lockout threshold",
                  ttk.Entry(g, textvariable=self._v("lockout_threshold", "3"),
                            width=8), r)
        self._row(g, "Lockout duration (s)",
                  ttk.Entry(g, textvariable=self._v("lockout_duration", "300"),
                            width=8), r, 2); r += 1
        self._row(g, "HTTPS admin port",
                  ttk.Entry(g, textvariable=self._v("admin_https_port"),
                            width=8), r)
        ttk.Checkbutton(g, text="strong-crypto",
                        variable=self._b("strong_crypto", True)).grid(
            row=r, column=2, sticky="w", padx=(10, 0))
        ttk.Checkbutton(g, text="password policy",
                        variable=self._b("password_policy", True)).grid(
            row=r, column=3, sticky="w"); r += 1
        self._row(g, "DNS primary",
                  ttk.Entry(g, textvariable=self._v("dns_primary")), r)
        self._row(g, "DNS secondary",
                  ttk.Entry(g, textvariable=self._v("dns_secondary")), r, 2)

        self.editors["ntp"] = ListEditor(
            t, "NTP servers", [("server", "Server")],
            [F("server", "NTP server (host/IP)")], height=2)
        self.editors["ntp"].pack(fill="x", pady=3)

        self.editors["admins"] = ListEditor(
            t, "Admin accounts", [("name", "Name"), ("profile", "Profile"),
                                  ("trusthost", "Trusted hosts")],
            [F("name", "Username"), F("password", "Password", "password"),
             F("profile", "Access profile", "text", "super_admin"),
             F("trusthost", "Trusted hosts (CIDR, comma-sep)")], height=2)
        self.editors["admins"].pack(fill="x", pady=3)

        self.editors["interfaces"] = ListEditor(
            t, "Interfaces", [("name", "Port"), ("alias", "Alias"),
                              ("role", "Role"), ("ip", "IP")],
            [F("name", "Interface (e.g. port1)"), F("alias", "Alias"),
             F("role", "Role", "choice", "lan",
               ["lan", "wan", "dmz", "undefined"]),
             F("mode", "Mode", "choice", "static", ["static", "dhcp", "pppoe"]),
             F("ip", "IP address"), F("mask", "Netmask", "text", "255.255.255.0"),
             F("allowaccess", "Admin access", "text", "ping https ssh"),
             F("description", "Description")], height=3)
        self.editors["interfaces"].pack(fill="x", pady=3)

        self.editors["static_routes"] = ListEditor(
            t, "Static routes", [("dst", "Destination"), ("gateway", "Gateway"),
                                 ("device", "Device")],
            [F("dst", "Destination", "text", "0.0.0.0 0.0.0.0"),
             F("gateway", "Gateway IP"), F("device", "Egress interface")],
            height=2)
        self.editors["static_routes"].pack(fill="x", pady=3)

        self.editors["dhcp"] = ListEditor(
            t, "DHCP servers", [("interface", "Interface"), ("start", "Start"),
                                ("end", "End")],
            [F("interface", "Interface"), F("gateway", "Default gateway"),
             F("netmask", "Netmask", "text", "255.255.255.0"),
             F("start", "Range start IP"), F("end", "Range end IP"),
             F("dns_server", "DNS server (blank=default)"),
             F("lease", "Lease seconds", "text", "86400")], height=2)
        self.editors["dhcp"].pack(fill="x", pady=3)

    def _tab_day1(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="Day 1 — Policies")
        self.editors["addresses"] = ListEditor(
            t, "Address objects", [("name", "Name"), ("type", "Type"),
                                   ("value", "Value")],
            [F("name", "Name"),
             F("type", "Type", "choice", "subnet",
               ["subnet", "iprange", "fqdn"]),
             F("value", "Value (subnet 'ip mask' / range a-b / fqdn)")],
            height=3)
        self.editors["addresses"].pack(fill="x", pady=3)

        self.editors["addrgrps"] = ListEditor(
            t, "Address groups", [("name", "Name"), ("members", "Members")],
            [F("name", "Group name"), F("members", "Members (space/comma-sep)")],
            height=2)
        self.editors["addrgrps"].pack(fill="x", pady=3)

        self.editors["ippools"] = ListEditor(
            t, "IP pools (SNAT)", [("name", "Name"), ("startip", "Start"),
                                   ("endip", "End")],
            [F("name", "Name"),
             F("type", "Type", "choice", "overload",
               ["overload", "one-to-one"]),
             F("startip", "Start IP"), F("endip", "End IP")], height=2)
        self.editors["ippools"].pack(fill="x", pady=3)

        self.editors["vips"] = ListEditor(
            t, "VIPs (port-forward / DNAT)",
            [("name", "Name"), ("extip", "External"), ("mappedip", "Internal"),
             ("extport", "Port")],
            [F("name", "Name"), F("extintf", "External interface"),
             F("extip", "External IP"), F("mappedip", "Internal IP"),
             F("protocol", "Protocol", "choice", "tcp", ["tcp", "udp"]),
             F("extport", "External port (blank=all)"),
             F("mappedport", "Internal port")], height=2)
        self.editors["vips"].pack(fill="x", pady=3)

        self.editors["policies"] = ListEditor(
            t, "Firewall policies",
            [("name", "Name"), ("srcintf", "Src"), ("dstintf", "Dst"),
             ("action", "Action")],
            [F("name", "Policy name"),
             F("srcintf", "Source interface(s)"),
             F("dstintf", "Dest interface(s)"),
             F("srcaddr", "Source address(es)", "text", "all"),
             F("dstaddr", "Dest address(es)", "text", "all"),
             F("service", "Service(s)", "text", "ALL"),
             F("action", "Action", "choice", "accept", ["accept", "deny"]),
             F("nat", "Source NAT", "bool", True),
             F("ippool", "IP pool name (blank=interface NAT)"),
             F("log", "Logging", "choice", "all", ["all", "utm", "disable"]),
             F("av", "AntiVirus", "bool", False),
             F("webfilter", "Web filter", "bool", False),
             F("ips", "IPS", "bool", False),
             F("appctrl", "App control", "bool", False),
             F("ssl", "SSL inspection", "choice", "certificate",
               ["none", "certificate", "deep"])], height=4)
        self.editors["policies"].pack(fill="x", pady=3)

    def _tab_day2(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="Day 2+ — Operations")
        lg = ttk.LabelFrame(t, text="Logging", padding=8)
        lg.pack(fill="x", pady=3)
        lg.columnconfigure(1, weight=1)
        lg.columnconfigure(3, weight=1)
        self._row(lg, "Syslog server",
                  ttk.Entry(lg, textvariable=self._v("syslog_server")), 0)
        self._row(lg, "Syslog port",
                  ttk.Entry(lg, textvariable=self._v("syslog_port", "514"),
                            width=8), 0, 2)
        self._row(lg, "Syslog mode",
                  ttk.Combobox(lg, textvariable=self._v("syslog_mode", "udp"),
                               values=["udp", "legacy-reliable", "reliable"],
                               state="readonly", width=12), 1)
        self._row(lg, "FortiAnalyzer",
                  ttk.Entry(lg, textvariable=self._v("faz_server")), 1, 2)

        sn = ttk.LabelFrame(t, text="SNMP", padding=8)
        sn.pack(fill="x", pady=3)
        sn.columnconfigure(1, weight=1)
        sn.columnconfigure(3, weight=1)
        ttk.Checkbutton(sn, text="Enable SNMP",
                        variable=self._b("snmp_enabled", False)).grid(
            row=0, column=0, columnspan=4, sticky="w")
        self._row(sn, "Contact",
                  ttk.Entry(sn, textvariable=self._v("snmp_contact")), 1)
        self._row(sn, "Location",
                  ttk.Entry(sn, textvariable=self._v("snmp_location")), 1, 2)
        self.editors["snmp_comm"] = ListEditor(
            sn, "Communities", [("name", "Name"), ("hosts", "Hosts")],
            [F("name", "Community"), F("hosts", "Allowed hosts (CIDR)"),
             F("queries", "Allow queries", "bool", True),
             F("traps", "Send traps", "bool", False)], height=2)
        self.editors["snmp_comm"].grid(row=2, column=0, columnspan=4,
                                       sticky="ew", pady=(4, 0))

        ha = ttk.LabelFrame(t, text="High Availability (HA)", padding=8)
        ha.pack(fill="x", pady=3)
        ha.columnconfigure(1, weight=1)
        ha.columnconfigure(3, weight=1)
        ttk.Checkbutton(ha, text="Enable HA",
                        variable=self._b("ha_enabled", False)).grid(
            row=0, column=0, columnspan=4, sticky="w")
        self._row(ha, "Group name",
                  ttk.Entry(ha, textvariable=self._v("ha_group", "FGT-HA")), 1)
        self._row(ha, "Mode",
                  ttk.Combobox(ha, textvariable=self._v("ha_mode", "a-p"),
                               values=["a-p", "a-a"], state="readonly",
                               width=8), 1, 2)
        self._row(ha, "Group password",
                  ttk.Entry(ha, textvariable=self._v("ha_password"),
                            show="*"), 2)
        self._row(ha, "Heartbeat intf",
                  ttk.Entry(ha, textvariable=self._v("ha_hbdev", "port3")), 2, 2)
        self._row(ha, "Priority",
                  ttk.Entry(ha, textvariable=self._v("ha_priority", "128"),
                            width=8), 3)
        ttk.Checkbutton(ha, text="override",
                        variable=self._b("ha_override", False)).grid(
            row=3, column=2, sticky="w", padx=(10, 0))

        ttk.Checkbutton(t, text="Enable automatic FortiGuard updates",
                        variable=self._b("autoupdate", True)).pack(
            anchor="w", pady=(6, 0))

    # -- spec assembly -----------------------------------------------------
    def assemble_spec(self) -> Dict[str, Any]:
        g = lambda k: self.vars[k].get()

        def i(k, d=0):
            try:
                return int(str(g(k)).strip() or d)
            except ValueError:
                return d

        spec: Dict[str, Any] = {
            "hostname": g("hostname").strip() or "FortiGate",
            "timezone": g("timezone").strip(),
            "admin_timeout": i("admin_timeout", 10),
            "admin_ssh_port": i("admin_ssh_port", 0) or None,
            "admin_https_port": i("admin_https_port", 0) or None,
            "lockout_threshold": i("lockout_threshold", 0) or None,
            "lockout_duration": i("lockout_duration", 0) or None,
            "strong_crypto": g("strong_crypto"),
            "password_policy": g("password_policy"),
            "dns": {"primary": g("dns_primary").strip(),
                    "secondary": g("dns_secondary").strip()},
            "ntp": [x["server"] for x in self.editors["ntp"].get_items()
                    if x.get("server")],
            "admins": self.editors["admins"].get_items(),
            "interfaces": self.editors["interfaces"].get_items(),
            "static_routes": self.editors["static_routes"].get_items(),
            "dhcp": [self._clean_dhcp(d)
                     for d in self.editors["dhcp"].get_items()],
            "addresses": self.editors["addresses"].get_items(),
            "addrgrps": self.editors["addrgrps"].get_items(),
            "ippools": self.editors["ippools"].get_items(),
            "vips": self.editors["vips"].get_items(),
            "policies": [self._clean_policy(p)
                         for p in self.editors["policies"].get_items()],
        }
        if g("syslog_server").strip():
            spec["syslog"] = {"server": g("syslog_server").strip(),
                              "port": i("syslog_port", 514),
                              "mode": g("syslog_mode"), "facility": "local7"}
        if g("faz_server").strip():
            spec["fortianalyzer"] = {"server": g("faz_server").strip()}
        if g("snmp_enabled"):
            spec["snmp"] = {"enabled": True, "contact": g("snmp_contact"),
                            "location": g("snmp_location"),
                            "communities": self.editors["snmp_comm"].get_items()}
        if g("ha_enabled"):
            spec["ha"] = {"enabled": True, "group_name": g("ha_group"),
                          "mode": g("ha_mode"), "password": g("ha_password"),
                          "hbdev": g("ha_hbdev"), "priority": i("ha_priority",
                                                                128),
                          "override": g("ha_override")}
        spec["autoupdate"] = g("autoupdate")
        return spec

    @staticmethod
    def _clean_dhcp(d):
        out = dict(d)
        if not out.get("dns_server"):
            out.pop("dns_server", None)
        if out.get("lease"):
            try:
                out["lease"] = int(out["lease"])
            except ValueError:
                out.pop("lease", None)
        return out

    @staticmethod
    def _clean_policy(p):
        return {
            "name": p.get("name", ""), "srcintf": p.get("srcintf", "any"),
            "dstintf": p.get("dstintf", "any"), "srcaddr": p.get("srcaddr", "all"),
            "dstaddr": p.get("dstaddr", "all"), "service": p.get("service", "ALL"),
            "action": p.get("action", "accept"), "nat": bool(p.get("nat")),
            "ippool": p.get("ippool", ""), "log": p.get("log", "all"),
            "profiles": {"av": bool(p.get("av")),
                         "webfilter": bool(p.get("webfilter")),
                         "ips": bool(p.get("ips")),
                         "appctrl": bool(p.get("appctrl")),
                         "ssl": p.get("ssl", "certificate")},
        }

    # -- actions -----------------------------------------------------------
    def generate(self):
        try:
            config = fb.build_config(self.assemble_spec())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))
            return None
        self.output.delete("1.0", "end")
        self.output.insert("1.0", config)
        return config

    def copy(self):
        config = self.output.get("1.0", "end").strip() or self.generate()
        if config:
            self.clipboard_clear()
            self.clipboard_append(config)
            messagebox.showinfo("Copied", "FortiOS config copied to clipboard.")

    def save_config(self):
        config = self.output.get("1.0", "end").strip() or self.generate()
        if not config:
            return
        host = self.vars["hostname"].get().strip() or "fortigate"
        path = filedialog.asksaveasfilename(
            title="Save FortiGate config", defaultextension=".conf",
            initialfile=f"{host}.conf",
            filetypes=[("Config", "*.conf *.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(config + "\n")
            messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def save_spec(self):
        path = filedialog.asksaveasfilename(
            title="Save spec", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.assemble_spec(), fh, indent=2)
            messagebox.showinfo("Saved", f"Spec saved to:\n{path}")

    def load_spec(self):
        path = filedialog.askopenfilename(
            title="Load spec", filetypes=[("JSON", "*.json"),
                                          ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self.populate(json.load(fh))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"Could not load spec:\n{exc}")

    # -- populate from spec -----------------------------------------------
    def populate(self, spec: Dict[str, Any]):
        def setv(k, v):
            if k in self.vars:
                self.vars[k].set("" if v is None else v)

        setv("hostname", spec.get("hostname", ""))
        setv("timezone", spec.get("timezone", ""))
        setv("admin_timeout", spec.get("admin_timeout", 10))
        setv("admin_ssh_port", spec.get("admin_ssh_port", "") or "")
        setv("admin_https_port", spec.get("admin_https_port", "") or "")
        setv("lockout_threshold", spec.get("lockout_threshold", "") or "")
        setv("lockout_duration", spec.get("lockout_duration", "") or "")
        setv("strong_crypto", bool(spec.get("strong_crypto")))
        setv("password_policy", bool(spec.get("password_policy")))
        dns = spec.get("dns", {})
        setv("dns_primary", dns.get("primary", ""))
        setv("dns_secondary", dns.get("secondary", ""))
        self.editors["ntp"].set_items([{"server": s} for s in spec.get("ntp", [])])
        self.editors["admins"].set_items(spec.get("admins", []))
        self.editors["interfaces"].set_items(spec.get("interfaces", []))
        self.editors["static_routes"].set_items(spec.get("static_routes", []))
        self.editors["dhcp"].set_items(spec.get("dhcp", []))
        self.editors["addresses"].set_items(spec.get("addresses", []))
        self.editors["addrgrps"].set_items(spec.get("addrgrps", []))
        self.editors["ippools"].set_items(spec.get("ippools", []))
        self.editors["vips"].set_items(spec.get("vips", []))
        # flatten policies' profiles back into the editor rows
        prows = []
        for p in spec.get("policies", []):
            pr = {k: p.get(k, "") for k in ("name", "srcintf", "dstintf",
                                            "srcaddr", "dstaddr", "service",
                                            "action", "ippool", "log")}
            pr["nat"] = bool(p.get("nat"))
            prof = p.get("profiles", {}) or {}
            pr.update({"av": bool(prof.get("av")),
                       "webfilter": bool(prof.get("webfilter")),
                       "ips": bool(prof.get("ips")),
                       "appctrl": bool(prof.get("appctrl")),
                       "ssl": prof.get("ssl", "certificate")})
            prows.append(pr)
        self.editors["policies"].set_items(prows)
        sl = spec.get("syslog", {})
        setv("syslog_server", sl.get("server", ""))
        setv("syslog_port", sl.get("port", 514))
        setv("syslog_mode", sl.get("mode", "udp"))
        setv("faz_server", spec.get("fortianalyzer", {}).get("server", ""))
        snmp = spec.get("snmp", {})
        setv("snmp_enabled", bool(snmp.get("enabled")))
        setv("snmp_contact", snmp.get("contact", ""))
        setv("snmp_location", snmp.get("location", ""))
        self.editors["snmp_comm"].set_items(snmp.get("communities", []))
        ha = spec.get("ha", {})
        setv("ha_enabled", bool(ha.get("enabled")))
        setv("ha_group", ha.get("group_name", "FGT-HA"))
        setv("ha_mode", ha.get("mode", "a-p"))
        setv("ha_password", ha.get("password", ""))
        setv("ha_hbdev", ha.get("hbdev", "port3"))
        setv("ha_priority", ha.get("priority", 128))
        setv("ha_override", bool(ha.get("override")))
        setv("autoupdate", bool(spec.get("autoupdate", True)))
