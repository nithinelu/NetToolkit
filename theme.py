#!/usr/bin/env python3
"""
Shared visual theme for NetToolkit.

Call apply_theme(root) once on the main window; every ttk widget in the
panels then picks up the styling automatically. A few named styles are
provided for emphasis:

    Accent.TButton     - primary action buttons
    Header.TFrame      - the top banner
    HeaderTitle.TLabel / HeaderSub.TLabel
    Status.TLabel      - the bottom status bar
    Muted.TLabel       - secondary/grey text
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ---- palette ----
BG = "#eef2f7"          # app background
SURFACE = "#ffffff"     # cards / inputs / tables
ACCENT = "#1f4e78"      # deep blue (primary)
ACCENT2 = "#2e6fb0"     # lighter blue (selection)
ACCENT_ACTIVE = "#163a5a"
TEXT = "#1b2733"
MUTED = "#5b6b7b"
BORDER = "#cdd6e0"
TAB_BG = "#dde5ee"
STATUS_BG = "#e4ebf3"

# dark "terminal" panes (output / console Text widgets)
CONSOLE_BG = "#0f141a"
CONSOLE_FG = "#d6e0ea"
CONSOLE_GREEN_BG = "#0e1711"
CONSOLE_GREEN_FG = "#cfe6cf"

UI_FONT = ("Segoe UI", 10)
UI_BOLD = ("Segoe UI", 10, "bold")
MONO_FONT = ("Consolas", 10)


def apply_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass

    style.configure(".", background=BG, foreground=TEXT, font=UI_FONT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)

    style.configure("TLabelframe", background=BG, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT,
                    font=UI_BOLD)

    # buttons
    style.configure("TButton", padding=(10, 5), background=SURFACE,
                    foreground=TEXT, bordercolor=BORDER, focuscolor=BG,
                    relief="flat")
    style.map("TButton",
              background=[("active", "#e6edf5"), ("pressed", "#dbe5f0")],
              bordercolor=[("active", ACCENT2)])
    style.configure("Accent.TButton", padding=(14, 6), background=ACCENT,
                    foreground="white", font=UI_BOLD, relief="flat",
                    focuscolor=ACCENT)
    style.map("Accent.TButton",
              background=[("active", ACCENT_ACTIVE), ("pressed", ACCENT_ACTIVE)],
              foreground=[("disabled", "#b9c4cf")])

    # notebook tabs
    style.configure("TNotebook", background=BG, borderwidth=0,
                    tabmargins=(8, 8, 8, 0))
    style.configure("TNotebook.Tab", padding=(18, 9), background=TAB_BG,
                    foreground=MUTED, font=UI_BOLD, borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE)],
              foreground=[("selected", ACCENT)],
              expand=[("selected", (0, 0, 0, 0))])

    # inputs
    style.configure("TEntry", fieldbackground=SURFACE, bordercolor=BORDER,
                    borderwidth=1, relief="solid", padding=3)
    style.map("TEntry", bordercolor=[("focus", ACCENT2)])
    style.configure("TCombobox", fieldbackground=SURFACE, bordercolor=BORDER,
                    arrowcolor=ACCENT, padding=3)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)])
    style.configure("TCheckbutton", background=BG, foreground=TEXT)
    style.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT)])

    # tables
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, rowheight=24, borderwidth=1,
                    bordercolor=BORDER)
    style.map("Treeview", background=[("selected", ACCENT2)],
              foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=ACCENT, foreground="white",
                    font=("Segoe UI", 9, "bold"), relief="flat", padding=5)
    style.map("Treeview.Heading", background=[("active", ACCENT2)])

    # header + status bar
    style.configure("Header.TFrame", background=ACCENT)
    style.configure("HeaderTitle.TLabel", background=ACCENT, foreground="white",
                    font=("Segoe UI Semibold", 17))
    style.configure("HeaderSub.TLabel", background=ACCENT, foreground="#cfe0f0",
                    font=("Segoe UI", 9))
    style.configure("HeaderBadge.TLabel", background=ACCENT, foreground="white",
                    font=("Segoe UI", 22))
    style.configure("Status.TLabel", background=STATUS_BG, foreground=MUTED,
                    padding=6)

    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=BORDER)
    return style
