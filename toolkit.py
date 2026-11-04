#!/usr/bin/env python3
"""
NetToolkit
==========

A single windowed application combining three network tools as tabs:

  1. Backup         - back up Cisco device configs over SSH/Telnet
                      (single device or Excel batch, optional show tech-support)
  2. Config Builder - build copy-paste-ready switch/router configurations
  3. Converter      - translate switch configs between Cisco, Arista,
                      Aruba (AOS-CX), Huawei and HPE Comware

Run with:  python toolkit.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

import theme
from backup_panel import BackupPanel
from config_panel import ConfigPanel
from convert_panel import ConvertPanel


class Toolkit(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NetToolkit")
        self.geometry("1020x800")
        self.minsize(900, 640)
        theme.apply_theme(self)

        self._build_header()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        # Config Builder/Converter are stdlib-only; Backup needs netmiko at run time.
        nb.add(BackupPanel(nb), text="Backup")
        nb.add(ConfigPanel(nb), text="Config Builder")
        nb.add(ConvertPanel(nb), text="Converter")

        status = ttk.Label(
            self, style="Status.TLabel", anchor="w",
            text="Configs are generated and translated locally — review "
                 "before applying to any device.")
        status.pack(fill="x", side="bottom")

    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text="\U0001F5A7", style="HeaderBadge.TLabel").pack(
            side="left", padx=(0, 12))
        box = ttk.Frame(header, style="Header.TFrame")
        box.pack(side="left")
        ttk.Label(box, text="NetToolkit", style="HeaderTitle.TLabel").pack(
            anchor="w")
        ttk.Label(box, style="HeaderSub.TLabel",
                  text="Backup  •  Config Builder  •  "
                       "Multi-vendor Converter").pack(anchor="w")


def main():
    try:
        app = Toolkit()
    except Exception as exc:  # noqa: BLE001
        # last-resort visibility if something fails before the window shows
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("NetToolkit failed to start", str(exc))
        raise
    app.mainloop()


if __name__ == "__main__":
    main()
