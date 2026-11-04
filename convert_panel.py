#!/usr/bin/env python3
"""Converter tab for CiscoToolkit - embeddable ttk.Frame."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import vendor_convert as vc
import theme


class ConvertPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.v_from = tk.StringVar(value="cisco")
        self.v_to = tk.StringVar(value="huawei")
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="From:").pack(side="left")
        ttk.Combobox(bar, textvariable=self.v_from, values=vc.VENDORS,
                     state="readonly", width=10).pack(side="left", padx=(2, 10))
        ttk.Label(bar, text="To:").pack(side="left")
        ttk.Combobox(bar, textvariable=self.v_to, values=vc.VENDORS,
                     state="readonly", width=10).pack(side="left", padx=(2, 10))
        ttk.Button(bar, text="Load file...",
                   command=self.load_file).pack(side="left")
        ttk.Button(bar, text="Convert  →", style="Accent.TButton",
                   command=self.convert).pack(side="left", padx=6)
        ttk.Button(bar, text="Swap", command=self.swap).pack(side="left")
        ttk.Button(bar, text="Copy output",
                   command=self.copy).pack(side="left", padx=6)
        ttk.Button(bar, text="Save output...",
                   command=self.save).pack(side="left")

        ttk.Label(bar, style="Muted.TLabel", text="  (supported: " +
                  ", ".join(vc.VENDOR_LABELS[v] for v in vc.VENDORS) + ")").pack(
            side="left")

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.LabelFrame(paned, text="Source configuration (paste here)",
                              padding=4)
        self.src = tk.Text(left, wrap="none", undo=True,
                           background=theme.CONSOLE_BG, foreground=theme.CONSOLE_FG,
                           insertbackground=theme.CONSOLE_FG, font=theme.MONO_FONT,
                           relief="flat", borderwidth=0, padx=8, pady=6)
        self.src.pack(fill="both", expand=True)
        paned.add(left, weight=1)

        right = ttk.LabelFrame(paned, text="Converted output", padding=4)
        self.dst = tk.Text(right, wrap="none", background=theme.CONSOLE_GREEN_BG,
                           foreground=theme.CONSOLE_GREEN_FG,
                           insertbackground=theme.CONSOLE_GREEN_FG,
                           font=theme.MONO_FONT, relief="flat", borderwidth=0,
                           padx=8, pady=6)
        self.dst.pack(fill="both", expand=True)
        paned.add(right, weight=1)

        self.status = ttk.Label(self, text="Paste a config, choose vendors, "
                                "then Convert.", anchor="w", relief="sunken")
        self.status.pack(fill="x", pady=(6, 0))

    def load_file(self):
        path = filedialog.askopenfilename(
            title="Open source config",
            filetypes=[("Config/text", "*.txt *.cfg *.conf *.log"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.src.delete("1.0", "end")
                self.src.insert("1.0", fh.read())
            self.status.configure(text=f"Loaded {os.path.basename(path)}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))

    def swap(self):
        a, b = self.v_from.get(), self.v_to.get()
        self.v_from.set(b)
        self.v_to.set(a)

    def convert(self):
        text = self.src.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Nothing to convert",
                                   "Paste or load a source configuration first.")
            return
        src, dst = self.v_from.get(), self.v_to.get()
        if src == dst:
            messagebox.showinfo("Same vendor",
                                "Source and target vendors are the same.")
            return
        try:
            result, info = vc.convert(text, src, dst)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Conversion error", str(exc))
            return
        self.dst.delete("1.0", "end")
        self.dst.insert("1.0", result)
        self.status.configure(
            text=(f"{vc.VENDOR_LABELS[src]} -> {vc.VENDOR_LABELS[dst]}  |  "
                  f"host: {info['hostname'] or '(none)'}  |  "
                  f"VLANs: {info['vlans']}  interfaces: {info['interfaces']}  "
                  f"|  unconverted lines: {info['unparsed']}"))

    def copy(self):
        out = self.dst.get("1.0", "end").strip()
        if not out:
            messagebox.showinfo("Nothing to copy", "Convert something first.")
            return
        self.clipboard_clear()
        self.clipboard_append(out)
        messagebox.showinfo("Copied", "Converted config copied to clipboard.")

    def save(self):
        out = self.dst.get("1.0", "end").strip()
        if not out:
            messagebox.showinfo("Nothing to save", "Convert something first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save converted config", defaultextension=".txt",
            initialfile=f"{self.v_to.get()}_config.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
