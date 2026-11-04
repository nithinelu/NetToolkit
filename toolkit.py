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

Author : Nithin Eluvathingal
License: MIT (see LICENSE)

Run with:  python toolkit.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import about
import theme
from backup_panel import BackupPanel
from config_panel import ConfigPanel
from convert_panel import ConvertPanel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Toolkit(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{about.APP_NAME} {about.VERSION}")
        self.geometry("1020x820")
        self.minsize(900, 660)
        theme.apply_theme(self)

        self._build_menu()
        self._build_header()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        # Config Builder/Converter are stdlib-only; Backup needs netmiko at run.
        nb.add(BackupPanel(nb), text="Backup")
        nb.add(ConfigPanel(nb), text="Config Builder")
        nb.add(ConvertPanel(nb), text="Converter")

        self._build_status()
        self.bind("<Control-q>", lambda e: self.destroy())
        self.bind("<F1>", lambda e: self.show_about())

    # ---- chrome ----------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Exit", accelerator="Ctrl+Q",
                             command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Open README",
                             command=lambda: self._open("README.md"))
        helpmenu.add_command(label="View License",
                             command=lambda: self._open("LICENSE"))
        helpmenu.add_separator()
        helpmenu.add_command(label="About " + about.APP_NAME,
                             accelerator="F1", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.config(menu=menubar)

    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(16, 12))
        header.pack(fill="x")
        ttk.Label(header, text="\U0001F5A7", style="HeaderBadge.TLabel").pack(
            side="left", padx=(0, 12))
        box = ttk.Frame(header, style="Header.TFrame")
        box.pack(side="left")
        ttk.Label(box, text=about.APP_NAME, style="HeaderTitle.TLabel").pack(
            anchor="w")
        ttk.Label(box, text=about.TAGLINE, style="HeaderSub.TLabel").pack(
            anchor="w")
        # right side: version + author
        right = ttk.Frame(header, style="Header.TFrame")
        right.pack(side="right")
        ttk.Label(right, text=f"v{about.VERSION}",
                  style="HeaderSub.TLabel").pack(anchor="e")
        ttk.Label(right, text=f"by {about.AUTHOR}",
                  style="HeaderSub.TLabel").pack(anchor="e")

    def _build_status(self):
        bar = ttk.Frame(self, style="Status.TFrame")
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, style="Status.TLabel", anchor="w",
                  text="Configs are generated and translated locally — "
                       "review before applying to any device.").pack(
            side="left")
        link = ttk.Label(bar, style="Status.TLabel", anchor="e", cursor="hand2",
                         text=f"{about.COPYRIGHT}  •  {about.LICENSE}  "
                              f"•  v{about.VERSION}")
        link.pack(side="right", padx=(0, 8))
        link.bind("<Button-1>", lambda e: self.show_about())

    # ---- actions ---------------------------------------------------------
    def _open(self, filename):
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            messagebox.showinfo(about.APP_NAME, f"{filename} not found.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo(about.APP_NAME, f"Could not open {filename}:\n{exc}")

    def show_about(self):
        AboutDialog(self)


class AboutDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"About {about.APP_NAME}")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=theme.SURFACE)

        wrap = ttk.Frame(self, padding=20)
        wrap.pack(fill="both", expand=True)
        wrap.configure(style="Card.TFrame")

        ttk.Label(wrap, text=f"\U0001F5A7  {about.APP_NAME}",
                  font=("Segoe UI Semibold", 16),
                  foreground=theme.ACCENT, background=theme.SURFACE).pack(
            anchor="w")
        ttk.Label(wrap, text=f"Version {about.VERSION}",
                  foreground=theme.MUTED, background=theme.SURFACE).pack(
            anchor="w", pady=(0, 10))
        ttk.Label(wrap, text=about.DESCRIPTION, justify="left", wraplength=420,
                  background=theme.SURFACE).pack(anchor="w")
        ttk.Separator(wrap).pack(fill="x", pady=12)
        ttk.Label(wrap, text=about.LICENSE_BLURB, justify="left",
                  wraplength=420, foreground=theme.MUTED,
                  background=theme.SURFACE).pack(anchor="w")
        ttk.Label(wrap, text=about.COPYRIGHT, font=("Segoe UI", 9, "bold"),
                  background=theme.SURFACE).pack(anchor="w", pady=(12, 0))

        btns = ttk.Frame(wrap, style="Card.TFrame")
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="View full license",
                   command=lambda: parent._open("LICENSE")).pack(side="left")
        ttk.Button(btns, text="Close", style="Accent.TButton",
                   command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.update_idletasks()
        # centre over parent
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")


def main():
    try:
        app = Toolkit()
    except Exception as exc:  # noqa: BLE001
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(f"{about.APP_NAME} failed to start", str(exc))
        raise
    app.mainloop()


if __name__ == "__main__":
    main()
