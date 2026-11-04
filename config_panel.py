#!/usr/bin/env python3
"""Config Builder tab for CiscoToolkit - embeddable ttk.Frame."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Any, Dict, List, Optional

import config_builder as cb
import theme


def F(key: str, label: str, kind: str = "text", default: Any = "",
      options: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"key": key, "label": label, "kind": kind, "default": default,
            "options": options or []}


class FormDialog(tk.Toplevel):
    def __init__(self, parent, title: str, fields: List[Dict[str, Any]],
                 initial: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result: Optional[Dict[str, Any]] = None
        self.fields = fields
        self.widgets: Dict[str, Any] = {}
        initial = initial or {}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        for r, f in enumerate(fields):
            ttk.Label(frm, text=f["label"] + ":").grid(row=r, column=0,
                                                       sticky="nw",
                                                       padx=(0, 8), pady=3)
            val = initial.get(f["key"], f["default"])
            kind = f["kind"]
            if kind == "bool":
                var = tk.BooleanVar(value=bool(val))
                ttk.Checkbutton(frm, variable=var).grid(row=r, column=1,
                                                        sticky="w", pady=3)
                self.widgets[f["key"]] = ("bool", var)
            elif kind == "choice":
                var = tk.StringVar(value=str(val) if val else f["options"][0])
                ttk.Combobox(frm, textvariable=var, values=f["options"],
                             state="readonly", width=24).grid(row=r, column=1,
                                                              sticky="ew", pady=3)
                self.widgets[f["key"]] = ("choice", var)
            elif kind == "multiline":
                txt = tk.Text(frm, width=34, height=5)
                if val:
                    txt.insert("1.0", val if isinstance(val, str)
                               else "\n".join(val))
                txt.grid(row=r, column=1, sticky="ew", pady=3)
                self.widgets[f["key"]] = ("multiline", txt)
            else:
                var = tk.StringVar(value="" if val in (None, "") else str(val))
                show = "*" if kind == "password" else ""
                ttk.Entry(frm, textvariable=var, show=show, width=26).grid(
                    row=r, column=1, sticky="ew", pady=3)
                self.widgets[f["key"]] = (kind, var)
        btns = ttk.Frame(frm)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="e",
                  pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(
            side="right", padx=4)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _ok(self):
        out: Dict[str, Any] = {}
        for f in self.fields:
            kind, w = self.widgets[f["key"]]
            if kind == "bool":
                out[f["key"]] = w.get()
                continue
            if kind == "multiline":
                out[f["key"]] = w.get("1.0", "end").strip()
                continue
            raw = w.get().strip()
            if kind == "int":
                if raw == "":
                    out[f["key"]] = 0
                else:
                    try:
                        out[f["key"]] = int(raw)
                    except ValueError:
                        return self._err(f["label"], "must be a whole number")
            elif kind == "ip":
                if not cb.is_valid_ip(raw):
                    return self._err(f["label"], "must be a valid IP address")
                out[f["key"]] = raw
            elif kind == "ipopt":
                if raw and not cb.is_valid_ip(raw):
                    return self._err(f["label"], "must be a valid IP (or blank)")
                out[f["key"]] = raw
            elif kind == "mask":
                if raw == "":
                    return self._err(f["label"], "is required")
                try:
                    out[f["key"]] = cb.normalize_mask(raw)
                except ValueError:
                    return self._err(f["label"],
                                     "must be a mask (255.255.255.0 or /24)")
            else:
                out[f["key"]] = raw
        self.result = out
        self.destroy()

    def _err(self, label, msg):
        messagebox.showwarning("Invalid input", f"{label} {msg}.", parent=self)


def open_form(parent, title, fields, initial=None):
    dlg = FormDialog(parent, title, fields, initial)
    parent.wait_window(dlg)
    return dlg.result


class ListEditor(ttk.LabelFrame):
    def __init__(self, parent, title, columns, fields, height=4):
        super().__init__(parent, text=title, padding=6)
        self.columns = columns
        self.fields = fields
        self.items: List[Dict[str, Any]] = []
        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings",
                                 height=height)
        for key, head in columns:
            self.tree.heading(key, text=head)
            self.tree.column(key, width=120, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        bar = ttk.Frame(self)
        bar.pack(side="left", fill="y", padx=(6, 0))
        ttk.Button(bar, text="Add", command=self.add, width=8).pack(pady=2)
        ttk.Button(bar, text="Edit", command=self.edit, width=8).pack(pady=2)
        ttk.Button(bar, text="Remove", command=self.remove, width=8).pack(pady=2)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.tag_configure("odd", background="#f3f6fa")
        self.tree.tag_configure("even", background="#ffffff")
        for i, item in enumerate(self.items):
            self.tree.insert("", "end", iid=str(i),
                             tags=("odd" if i % 2 else "even",),
                             values=[item.get(c[0], "") for c in self.columns])

    def add(self):
        res = open_form(self.winfo_toplevel(), f"Add - {self['text']}",
                        self.fields)
        if res is not None:
            self.items.append(res)
            self._refresh()

    def edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        res = open_form(self.winfo_toplevel(), f"Edit - {self['text']}",
                        self.fields, self.items[idx])
        if res is not None:
            self.items[idx] = res
            self._refresh()

    def remove(self):
        sel = self.tree.selection()
        if not sel:
            return
        del self.items[int(sel[0])]
        self._refresh()

    def get_items(self):
        return [dict(i) for i in self.items]

    def set_items(self, items):
        self.items = [dict(i) for i in (items or [])]
        self._refresh()


class ConfigPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.vars: Dict[str, tk.Variable] = {}
        self.editors: Dict[str, ListEditor] = {}
        self._build()

    def _v(self, key, default=""):
        self.vars[key] = tk.StringVar(value=default)
        return self.vars[key]

    def _b(self, key, default=False):
        self.vars[key] = tk.BooleanVar(value=default)
        return self.vars[key]

    def _labeled(self, parent, label, widget, r, c=0):
        ttk.Label(parent, text=label).grid(row=r, column=c, sticky="w",
                                           padx=(0, 8), pady=3)
        widget.grid(row=r, column=c + 1, sticky="ew", pady=3)

    def _build(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Generate config", style="Accent.TButton",
                   command=self.generate).pack(side="left")
        ttk.Button(bar, text="Copy", command=self.copy).pack(side="left", padx=4)
        ttk.Button(bar, text="Save config...",
                   command=self.save_config).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=8)
        ttk.Button(bar, text="Load spec...",
                   command=self.load_spec).pack(side="left")
        ttk.Button(bar, text="Save spec...",
                   command=self.save_spec).pack(side="left", padx=4)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self._tab_general(nb)
        self._tab_l2(nb)
        self._tab_l3(nb)
        self._tab_routing(nb)
        self._tab_services(nb)
        out = ttk.LabelFrame(self, text="Generated configuration", padding=6)
        out.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.output = tk.Text(out, height=10, wrap="none",
                              background=theme.CONSOLE_BG,
                              foreground=theme.CONSOLE_FG, font=theme.MONO_FONT,
                              relief="flat", borderwidth=0, padx=8, pady=6)
        self.output.pack(fill="both", expand=True)

    def _tab_general(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="General")
        t.columnconfigure(1, weight=1)
        r = 0
        self._labeled(t, "Device type",
                      ttk.Combobox(t, textvariable=self._v("role", "switch"),
                                   values=["switch", "router"],
                                   state="readonly"), r); r += 1
        self._labeled(t, "Hostname",
                      ttk.Entry(t, textvariable=self._v("hostname")), r); r += 1
        self._labeled(t, "Domain name",
                      ttk.Entry(t, textvariable=self._v("domain")), r); r += 1
        self._labeled(t, "Enable secret",
                      ttk.Entry(t, textvariable=self._v("enable_secret"),
                                show="*"), r); r += 1
        self._labeled(t, "Login banner",
                      ttk.Entry(t, textvariable=self._v("banner")), r); r += 1
        ttk.Checkbutton(t, text="service password-encryption",
                        variable=self._b("password_encryption", True)).grid(
            row=r, column=1, sticky="w"); r += 1
        ttk.Checkbutton(t, text="no ip domain-lookup",
                        variable=self._b("no_domain_lookup", True)).grid(
            row=r, column=1, sticky="w"); r += 1
        ttk.Separator(t, orient="horizontal").grid(row=r, column=0,
                                                   columnspan=2, sticky="ew",
                                                   pady=8); r += 1
        ttk.Label(t, text="Remote access", font=("", 9, "bold")).grid(
            row=r, column=0, sticky="w"); r += 1
        ttk.Checkbutton(t, text="Enable SSH (recommended)",
                        variable=self._b("ssh", True)).grid(row=r, column=1,
                                                            sticky="w"); r += 1
        self._labeled(t, "RSA key modulus",
                      ttk.Entry(t, textvariable=self._v("modulus", "2048"),
                                width=10), r); r += 1
        ttk.Checkbutton(t, text="Enable Telnet (insecure)",
                        variable=self._b("telnet", False)).grid(row=r, column=1,
                                                                sticky="w"); r += 1
        self._labeled(t, "Line exec-timeout",
                      ttk.Entry(t, textvariable=self._v("exec_timeout", "10 0"),
                                width=10), r); r += 1
        self._labeled(t, "VTY password (if no users)",
                      ttk.Entry(t, textvariable=self._v("vty_password"),
                                show="*"), r); r += 1
        users = ListEditor(t, "Local users",
                           [("username", "Username"), ("privilege", "Priv"),
                            ("password", "Password")],
                           [F("username", "Username"),
                            F("password", "Password", "password"),
                            F("privilege", "Privilege (blank=1)", "int", 15)])
        users.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.editors["users"] = users

    def _tab_l2(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="VLANs & Switchports")
        self.editors["vlans"] = ListEditor(
            t, "VLANs", [("id", "ID"), ("name", "Name")],
            [F("id", "VLAN ID", "int", 10), F("name", "Name")])
        self.editors["vlans"].pack(fill="x", pady=4)
        self.editors["access_ports"] = ListEditor(
            t, "Access ports",
            [("interface", "Interface"), ("vlan", "VLAN"),
             ("description", "Description")],
            [F("interface", "Interface or range"),
             F("vlan", "Access VLAN", "int", 1), F("description", "Description"),
             F("voice_vlan", "Voice VLAN (0=none)", "int", 0),
             F("portfast", "PortFast", "bool", True),
             F("bpduguard", "BPDU guard", "bool", True)])
        self.editors["access_ports"].pack(fill="x", pady=4)
        self.editors["trunk_ports"] = ListEditor(
            t, "Trunk ports",
            [("interface", "Interface"), ("native", "Native"),
             ("allowed", "Allowed")],
            [F("interface", "Interface or range"), F("description", "Description"),
             F("native", "Native VLAN (0=default)", "int", 0),
             F("allowed", "Allowed VLANs (blank=all)"),
             F("encapsulation_dot1q", "encapsulation dot1q (old switches)",
               "bool", False)])
        self.editors["trunk_ports"].pack(fill="x", pady=4)
        self.editors["etherchannels"] = ListEditor(
            t, "EtherChannels (port-channels)",
            [("id", "PC#"), ("members", "Members"), ("mode", "Mode"),
             ("type", "Type")],
            [F("id", "Port-channel number", "int", 1),
             F("members", "Member interfaces (range/CSV)"),
             F("mode", "Mode", "choice", "active",
               ["active", "passive", "on", "desirable", "auto"]),
             F("type", "Type", "choice", "trunk", ["trunk", "access", "l3"]),
             F("description", "Description"),
             F("vlan", "Access VLAN (access type)", "int", 0),
             F("native", "Native VLAN (trunk, 0=def)", "int", 0),
             F("allowed", "Allowed VLANs (trunk)"),
             F("ip", "IP (l3 type)", "ipopt"), F("mask", "Mask (l3 type)")])
        self.editors["etherchannels"].pack(fill="x", pady=4)

    def _tab_l3(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="IP & Interfaces")
        mg = ttk.LabelFrame(t, text="Management IP", padding=8)
        mg.pack(fill="x", pady=4)
        mg.columnconfigure(1, weight=1)
        mg.columnconfigure(3, weight=1)
        ttk.Checkbutton(mg, text="Configure management IP",
                        variable=self._b("mgmt_enable", True)).grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(mg, text="(switch) VLAN").grid(row=1, column=0, sticky="w")
        ttk.Entry(mg, textvariable=self._v("mgmt_vlan", "1"), width=8).grid(
            row=1, column=1, sticky="w")
        ttk.Label(mg, text="(router) Interface").grid(row=1, column=2,
                                                      sticky="w", padx=(10, 0))
        ttk.Entry(mg, textvariable=self._v("mgmt_interface")).grid(
            row=1, column=3, sticky="ew")
        ttk.Label(mg, text="IP").grid(row=2, column=0, sticky="w")
        ttk.Entry(mg, textvariable=self._v("mgmt_ip")).grid(row=2, column=1,
                                                           sticky="ew")
        ttk.Label(mg, text="Mask").grid(row=2, column=2, sticky="w", padx=(10, 0))
        ttk.Entry(mg, textvariable=self._v("mgmt_mask", "255.255.255.0")).grid(
            row=2, column=3, sticky="ew")
        ttk.Label(mg, text="Gateway (switch)").grid(row=3, column=0, sticky="w")
        ttk.Entry(mg, textvariable=self._v("mgmt_gateway")).grid(
            row=3, column=1, sticky="ew")
        self.editors["l3_interfaces"] = ListEditor(
            t, "Routed (L3) interfaces",
            [("interface", "Interface"), ("ip", "IP"), ("mask", "Mask")],
            [F("interface", "Interface"), F("description", "Description"),
             F("ip", "IP address", "ip"), F("mask", "Subnet mask", "mask")])
        self.editors["l3_interfaces"].pack(fill="x", pady=4)
        self.editors["hsrp"] = ListEditor(
            t, "First-hop redundancy (HSRP/VRRP)",
            [("protocol", "Proto"), ("interface", "Interface"),
             ("group", "Grp"), ("vip", "Virtual IP")],
            [F("protocol", "Protocol", "choice", "hsrp", ["hsrp", "vrrp"]),
             F("interface", "Interface (e.g. Vlan10)"),
             F("group", "Group", "int", 1), F("vip", "Virtual IP", "ip"),
             F("priority", "Priority (0=default)", "int", 0),
             F("preempt", "Preempt", "bool", True),
             F("version", "HSRP version 2", "bool", True)])
        self.editors["hsrp"].pack(fill="x", pady=4)

    def _tab_routing(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="Routing")
        df = ttk.LabelFrame(t, text="Default route", padding=8)
        df.pack(fill="x", pady=4)
        ttk.Checkbutton(df, text="Add default route (0.0.0.0/0)",
                        variable=self._b("default_route", False)).pack(
            side="left")
        ttk.Label(df, text="  next-hop:").pack(side="left")
        ttk.Entry(df, textvariable=self._v("default_gw"), width=18).pack(
            side="left")
        self.editors["static_routes"] = ListEditor(
            t, "Static routes",
            [("network", "Network"), ("mask", "Mask"), ("next_hop", "Next-hop")],
            [F("network", "Destination network", "ip"),
             F("mask", "Network mask", "mask"), F("next_hop", "Next-hop IP", "ip")])
        self.editors["static_routes"].pack(fill="x", pady=4)
        of = ttk.LabelFrame(t, text="OSPF", padding=8)
        of.pack(fill="x", pady=4)
        ttk.Checkbutton(of, text="Configure OSPF",
                        variable=self._b("ospf_enable", False)).grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(of, text="Process id").grid(row=1, column=0, sticky="w")
        ttk.Entry(of, textvariable=self._v("ospf_process", "1"), width=8).grid(
            row=1, column=1, sticky="w")
        ttk.Label(of, text="Router-id").grid(row=1, column=2, sticky="w",
                                             padx=(10, 0))
        ttk.Entry(of, textvariable=self._v("ospf_rid"), width=16).grid(
            row=1, column=3, sticky="w")
        self.editors["ospf_networks"] = ListEditor(
            of, "OSPF networks",
            [("network", "Network"), ("mask", "Mask"), ("area", "Area")],
            [F("network", "Network", "ip"), F("mask", "Mask", "mask"),
             F("area", "Area", "text", "0")], height=3)
        self.editors["ospf_networks"].grid(row=2, column=0, columnspan=4,
                                           sticky="ew", pady=(6, 0))

    def _tab_services(self, nb):
        t = ttk.Frame(nb, padding=12)
        nb.add(t, text="Services & Security")
        ipf = [F("ip", "IP address", "ip")]
        cols = [("ip", "IP")]
        for key, title in (("dns", "DNS name-servers"), ("ntp", "NTP servers"),
                           ("logging", "Syslog hosts")):
            ed = ListEditor(t, title, cols, ipf, height=2)
            ed.pack(fill="x", pady=3)
            self.editors[key] = ed
        self.editors["dhcp_excluded"] = ListEditor(
            t, "DHCP excluded ranges",
            [("lo", "First IP"), ("hi", "Last IP")],
            [F("lo", "First IP", "ip"), F("hi", "Last IP (blank=one)", "ipopt")],
            height=2)
        self.editors["dhcp_excluded"].pack(fill="x", pady=3)
        self.editors["dhcp_pools"] = ListEditor(
            t, "DHCP pools",
            [("name", "Name"), ("network", "Network"), ("gateway", "Gateway")],
            [F("name", "Pool name"), F("network", "Network", "ip"),
             F("mask", "Mask", "mask"), F("gateway", "Gateway", "ipopt"),
             F("dns", "DNS servers (space/comma)"), F("domain", "Domain name"),
             F("lease", "Lease 'days hours minutes'")], height=2)
        self.editors["dhcp_pools"].pack(fill="x", pady=3)
        self.editors["acls"] = ListEditor(
            t, "Access lists",
            [("name", "Name"), ("type", "Type"), ("apply_interface", "Applied to")],
            [F("name", "ACL name or number"),
             F("type", "Type", "choice", "extended", ["extended", "standard"]),
             F("entries", "Entries (one per line)", "multiline"),
             F("apply_interface", "Apply to interface (optional)"),
             F("direction", "Direction", "choice", "in", ["in", "out"]),
             F("apply_vty", "Apply to VTY (remote filter)", "bool", False)],
            height=2)
        self.editors["acls"].pack(fill="x", pady=3)
        sn = ttk.LabelFrame(t, text="SNMP", padding=6)
        sn.pack(fill="x", pady=3)
        ttk.Checkbutton(sn, text="Configure SNMP",
                        variable=self._b("snmp_enable", False)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(sn, text="Location").grid(row=1, column=0, sticky="w")
        ttk.Entry(sn, textvariable=self._v("snmp_location"), width=30).grid(
            row=1, column=1, sticky="w")
        ttk.Label(sn, text="Contact").grid(row=2, column=0, sticky="w")
        ttk.Entry(sn, textvariable=self._v("snmp_contact"), width=30).grid(
            row=2, column=1, sticky="w")
        self.editors["snmp_comm"] = ListEditor(
            sn, "Communities", [("community", "Community"), ("mode", "Mode")],
            [F("community", "Community"),
             F("mode", "Access", "choice", "ro", ["ro", "rw"])], height=2)
        self.editors["snmp_comm"].grid(row=3, column=0, columnspan=2,
                                       sticky="ew", pady=(4, 0))
        self.editors["snmp_hosts"] = ListEditor(
            sn, "Trap hosts", [("host", "Host"), ("community", "Community")],
            [F("host", "Host IP", "ip"), F("community", "Community")], height=2)
        self.editors["snmp_hosts"].grid(row=4, column=0, columnspan=2,
                                        sticky="ew", pady=(4, 0))

    def assemble_spec(self) -> Dict[str, Any]:
        g = lambda k: self.vars[k].get()
        role = g("role")
        spec: Dict[str, Any] = {
            "role": role, "hostname": g("hostname").strip(),
            "domain": g("domain").strip(), "enable_secret": g("enable_secret"),
            "banner": g("banner").strip(),
            "services": {
                "password_encryption": g("password_encryption"),
                "no_domain_lookup": g("no_domain_lookup"),
                "dns": [i["ip"] for i in self.editors["dns"].get_items()],
                "ntp": [i["ip"] for i in self.editors["ntp"].get_items()],
                "logging": [i["ip"] for i in self.editors["logging"].get_items()],
            },
            "ssh": {"enable": g("ssh"), "version": 2,
                    "modulus": int(g("modulus") or 2048)},
            "telnet": g("telnet"),
            "vty": {"exec_timeout": g("exec_timeout") or "10 0"},
        }
        if g("vty_password"):
            spec["vty"]["password"] = g("vty_password")
        users = []
        for u in self.editors["users"].get_items():
            uu = {"username": u["username"], "password": u["password"]}
            if u.get("privilege"):
                uu["privilege"] = u["privilege"]
            users.append(uu)
        spec["users"] = users
        if g("mgmt_enable") and g("mgmt_ip"):
            if role == "switch":
                spec["management"] = {
                    "vlan": int(g("mgmt_vlan") or 1), "ip": g("mgmt_ip"),
                    "mask": cb.normalize_mask(g("mgmt_mask") or "255.255.255.0")}
                if g("mgmt_gateway"):
                    spec["management"]["gateway"] = g("mgmt_gateway")
            else:
                spec["management"] = {
                    "interface": g("mgmt_interface"), "ip": g("mgmt_ip"),
                    "mask": cb.normalize_mask(g("mgmt_mask") or "255.255.255.0")}
        spec["vlans"] = self.editors["vlans"].get_items()
        aps = []
        for p in self.editors["access_ports"].get_items():
            if not p.get("voice_vlan"):
                p.pop("voice_vlan", None)
            aps.append(p)
        spec["access_ports"] = aps
        tps = []
        for p in self.editors["trunk_ports"].get_items():
            if not p.get("native"):
                p.pop("native", None)
            if not p.get("allowed"):
                p.pop("allowed", None)
            tps.append(p)
        spec["trunk_ports"] = tps
        ecs = []
        for ec in self.editors["etherchannels"].get_items():
            kind = ec.get("type", "trunk")
            keep = {"id": ec["id"], "members": ec["members"],
                    "mode": ec.get("mode", "active"), "type": kind,
                    "description": ec.get("description", "")}
            if kind == "access" and ec.get("vlan"):
                keep["vlan"] = ec["vlan"]
            if kind == "trunk":
                if ec.get("native"):
                    keep["native"] = ec["native"]
                if ec.get("allowed"):
                    keep["allowed"] = ec["allowed"]
                keep["encapsulation_dot1q"] = ec.get("encapsulation_dot1q", False)
            if kind == "l3" and ec.get("ip"):
                keep["ip"] = ec["ip"]
                keep["mask"] = cb.normalize_mask(ec.get("mask") or "255.255.255.0")
            ecs.append(keep)
        spec["etherchannels"] = ecs
        spec["l3_interfaces"] = self.editors["l3_interfaces"].get_items()
        groups = []
        for gp in self.editors["hsrp"].get_items():
            keep = {"protocol": gp.get("protocol", "hsrp"),
                    "interface": gp["interface"], "group": gp.get("group", 1),
                    "vip": gp["vip"], "preempt": gp.get("preempt", True)}
            if gp.get("priority"):
                keep["priority"] = gp["priority"]
            if keep["protocol"] == "hsrp" and gp.get("version"):
                keep["version"] = 2
            groups.append(keep)
        spec["hsrp"] = groups
        routes = []
        if g("default_route") and g("default_gw"):
            routes.append({"network": "0.0.0.0", "mask": "0.0.0.0",
                           "next_hop": g("default_gw")})
        routes.extend(self.editors["static_routes"].get_items())
        spec["static_routes"] = routes
        if g("ospf_enable"):
            nets = []
            for n in self.editors["ospf_networks"].get_items():
                nets.append({"network": n["network"],
                             "wildcard": cb.mask_to_wildcard(n["mask"]),
                             "area": n.get("area", "0")})
            ospf = {"process": int(g("ospf_process") or 1), "networks": nets}
            if g("ospf_rid"):
                ospf["router_id"] = g("ospf_rid")
            spec["ospf"] = ospf
        excluded = [f"{i['lo']} {i.get('hi', '')}".strip()
                    for i in self.editors["dhcp_excluded"].get_items()]
        pools = []
        for p in self.editors["dhcp_pools"].get_items():
            pp = {"name": p["name"], "network": p["network"],
                  "mask": cb.normalize_mask(p["mask"])}
            if p.get("gateway"):
                pp["gateway"] = p["gateway"]
            if p.get("dns"):
                pp["dns"] = p["dns"].replace(",", " ").split()
            if p.get("domain"):
                pp["domain"] = p["domain"]
            if p.get("lease"):
                pp["lease"] = p["lease"]
            pools.append(pp)
        if excluded or pools:
            spec["dhcp"] = {"excluded": excluded, "pools": pools}
        acls = []
        for a in self.editors["acls"].get_items():
            aa = {"name": a["name"], "type": a.get("type", "extended"),
                  "entries": [ln.strip() for ln in
                              str(a.get("entries", "")).splitlines() if ln.strip()]}
            if a.get("apply_interface"):
                aa["apply_interface"] = a["apply_interface"]
                aa["direction"] = a.get("direction", "in")
            if a.get("apply_vty"):
                aa["apply_vty"] = True
            acls.append(aa)
        spec["acls"] = acls
        if g("snmp_enable"):
            spec["snmp"] = {
                "communities": self.editors["snmp_comm"].get_items(),
                "location": g("snmp_location"), "contact": g("snmp_contact"),
                "trap_hosts": self.editors["snmp_hosts"].get_items()}
        return spec

    def generate(self):
        if not self.vars["hostname"].get().strip():
            messagebox.showwarning("Missing", "Enter a hostname (General tab).")
            return None
        try:
            config = cb.build_config(self.assemble_spec())
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
            messagebox.showinfo("Copied", "Configuration copied to clipboard.")

    def save_config(self):
        config = self.output.get("1.0", "end").strip() or self.generate()
        if not config:
            return
        host = self.vars["hostname"].get().strip() or "device"
        path = filedialog.asksaveasfilename(
            title="Save config", defaultextension=".txt",
            initialfile=f"{host}.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(config + "\n")
            messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def save_spec(self):
        try:
            spec = self.assemble_spec()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Save spec", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=2)
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

    def populate(self, spec: Dict[str, Any]):
        def setv(k, v):
            if k in self.vars:
                self.vars[k].set(v if v is not None else "")
        setv("role", spec.get("role", "switch"))
        for k in ("hostname", "domain", "enable_secret", "banner"):
            setv(k, spec.get(k, ""))
        svc = spec.get("services", {})
        setv("password_encryption", svc.get("password_encryption", True))
        setv("no_domain_lookup", svc.get("no_domain_lookup", True))
        self.editors["dns"].set_items([{"ip": x} for x in svc.get("dns", [])])
        self.editors["ntp"].set_items([{"ip": x} for x in svc.get("ntp", [])])
        self.editors["logging"].set_items([{"ip": x}
                                           for x in svc.get("logging", [])])
        ssh = spec.get("ssh", {})
        setv("ssh", ssh.get("enable", True))
        setv("modulus", ssh.get("modulus", 2048))
        setv("telnet", spec.get("telnet", False))
        vty = spec.get("vty", {})
        setv("exec_timeout", vty.get("exec_timeout", "10 0"))
        setv("vty_password", vty.get("password", ""))
        self.editors["users"].set_items(spec.get("users", []))
        mg = spec.get("management")
        setv("mgmt_enable", bool(mg))
        if mg:
            setv("mgmt_vlan", mg.get("vlan", 1))
            setv("mgmt_interface", mg.get("interface", ""))
            setv("mgmt_ip", mg.get("ip", ""))
            setv("mgmt_mask", mg.get("mask", "255.255.255.0"))
            setv("mgmt_gateway", mg.get("gateway", ""))
        self.editors["vlans"].set_items(spec.get("vlans", []))
        self.editors["access_ports"].set_items(spec.get("access_ports", []))
        self.editors["trunk_ports"].set_items(spec.get("trunk_ports", []))
        self.editors["etherchannels"].set_items(spec.get("etherchannels", []))
        self.editors["l3_interfaces"].set_items(spec.get("l3_interfaces", []))
        self.editors["hsrp"].set_items(spec.get("hsrp", []))
        routes = list(spec.get("static_routes", []))
        default = next((r for r in routes if r.get("network") == "0.0.0.0"), None)
        if default:
            setv("default_route", True)
            setv("default_gw", default.get("next_hop", ""))
            routes = [r for r in routes if r is not default]
        self.editors["static_routes"].set_items(routes)
        ospf = spec.get("ospf")
        setv("ospf_enable", bool(ospf))
        if ospf:
            setv("ospf_process", ospf.get("process", 1))
            setv("ospf_rid", ospf.get("router_id", ""))
            self.editors["ospf_networks"].set_items(
                [{"network": n["network"],
                  "mask": cb.mask_to_wildcard(n["wildcard"]),
                  "area": n.get("area", "0")} for n in ospf.get("networks", [])])
        dhcp = spec.get("dhcp", {})
        excl = []
        for rng in dhcp.get("excluded", []):
            parts = rng.split()
            excl.append({"lo": parts[0], "hi": parts[1] if len(parts) > 1 else ""})
        self.editors["dhcp_excluded"].set_items(excl)
        self.editors["dhcp_pools"].set_items(
            [{**p, "dns": " ".join(p.get("dns", []))}
             for p in dhcp.get("pools", [])])
        self.editors["acls"].set_items(
            [{**a, "entries": "\n".join(a.get("entries", []))}
             for a in spec.get("acls", [])])
        snmp = spec.get("snmp")
        setv("snmp_enable", bool(snmp))
        if snmp:
            setv("snmp_location", snmp.get("location", ""))
            setv("snmp_contact", snmp.get("contact", ""))
            self.editors["snmp_comm"].set_items(snmp.get("communities", []))
            self.editors["snmp_hosts"].set_items(snmp.get("trap_hosts", []))
