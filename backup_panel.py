#!/usr/bin/env python3
"""Backup tab for CiscoToolkit - embeddable ttk.Frame."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cisco_backup as cb
import theme


class BackupPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.v_tech = tk.BooleanVar(value=False)
        self.v_tech_timeout = tk.StringVar(value=str(cb.TECH_READ_TIMEOUT))
        self._build()
        self.after(150, self._drain_log)

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="x")

        # single device
        single = ttk.Frame(nb, padding=12)
        nb.add(single, text="Single device")
        single.columnconfigure(1, weight=1)
        self.v_host = tk.StringVar()
        self.v_user = tk.StringVar()
        self.v_pass = tk.StringVar()
        self.v_secret = tk.StringVar()
        self.v_proto = tk.StringVar(value="ssh")
        self.v_family = tk.StringVar(value="ios")
        self.v_port = tk.StringVar()

        def row(label, widget, r):
            ttk.Label(single, text=label).grid(row=r, column=0, sticky="w",
                                               pady=4, padx=(0, 8))
            widget.grid(row=r, column=1, sticky="ew", pady=4)

        row("IP / Host:", ttk.Entry(single, textvariable=self.v_host), 0)
        row("Username:", ttk.Entry(single, textvariable=self.v_user), 1)
        row("Password:", ttk.Entry(single, textvariable=self.v_pass, show="*"), 2)
        row("Enable secret:",
            ttk.Entry(single, textvariable=self.v_secret, show="*"), 3)
        row("Protocol:", ttk.Combobox(single, textvariable=self.v_proto,
                                      values=["ssh", "telnet"],
                                      state="readonly"), 4)
        row("Family:", ttk.Combobox(single, textvariable=self.v_family,
                                    values=["ios", "xe", "nxos", "asa"],
                                    state="readonly"), 5)
        row("Port (optional):", ttk.Entry(single, textvariable=self.v_port), 6)
        ttk.Button(single, text="Back up this device", style="Accent.TButton",
                   command=self.run_single).grid(row=7, column=1, sticky="e",
                                                  pady=(10, 0))

        # excel
        excel = ttk.Frame(nb, padding=12)
        nb.add(excel, text="From Excel")
        excel.columnconfigure(1, weight=1)
        self.v_excel = tk.StringVar()
        ttk.Label(excel, text="Excel file:").grid(row=0, column=0, sticky="w",
                                                  padx=(0, 8))
        ttk.Entry(excel, textvariable=self.v_excel).grid(row=0, column=1,
                                                         sticky="ew")
        ttk.Button(excel, text="Browse...",
                   command=self.browse_excel).grid(row=0, column=2, padx=(8, 0))
        btns = ttk.Frame(excel)
        btns.grid(row=1, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Create template...",
                   command=self.create_template).pack(side="left", padx=4)
        ttk.Button(btns, text="Back up all devices", style="Accent.TButton",
                   command=self.run_excel).pack(side="left", padx=4)
        ttk.Label(excel, text=("Columns: host, protocol, family, username, "
                               "password, secret, port, name.\nOnly host, "
                               "username and password are required."),
                  foreground="#555").grid(row=2, column=0, columnspan=3,
                                          sticky="w", pady=(12, 0))

        # options
        opts = ttk.Frame(self)
        opts.pack(anchor="w", fill="x", pady=(8, 0))
        ttk.Checkbutton(opts, text="Also capture 'show tech-support' "
                        "(slow, large file)", variable=self.v_tech).pack(
            side="left")
        ttk.Label(opts, text="  timeout (s):").pack(side="left")
        ttk.Entry(opts, textvariable=self.v_tech_timeout, width=6).pack(
            side="left")

        ttk.Label(self, text="Output:").pack(anchor="w", pady=(10, 0))
        self.txt = tk.Text(self, height=14, wrap="none",
                           background=theme.CONSOLE_BG, foreground=theme.CONSOLE_FG,
                           insertbackground=theme.CONSOLE_FG, font=theme.MONO_FONT,
                           relief="flat", borderwidth=0, padx=8, pady=6)
        self.txt.pack(fill="both", expand=True, pady=(2, 4))
        self.txt.configure(state="disabled")
        self.status = ttk.Label(self, text="Ready", anchor="w", relief="sunken")
        self.status.pack(fill="x")

    def log(self, line: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _drain_log(self):
        try:
            while True:
                self.log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    def _busy(self, msg=""):
        self.status.configure(text=msg or "Ready")

    def _make_gui_logger(self):
        logger = cb.setup_logging()
        q = self.log_queue

        class QueueHandler(logging.Handler):
            def emit(self, record):
                q.put(self.format(record))

        h = QueueHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s",
                                         datefmt="%H:%M:%S"))
        logger.addHandler(h)
        return logger

    def _run(self, devices):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "A backup is already running.")
            return
        try:
            tech_timeout = int(self.v_tech_timeout.get().strip()
                               or cb.TECH_READ_TIMEOUT)
            if tech_timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid timeout",
                                   "Tech-support timeout must be a positive "
                                   "whole number.")
            return
        capture_tech = self.v_tech.get()

        def task():
            logger = self._make_gui_logger()
            self._busy("Working...")
            try:
                results = cb.backup_many(devices, logger,
                                         capture_tech=capture_tech,
                                         tech_timeout=tech_timeout)
                ok = sum(1 for r in results if r.success)
                msg = f"Done: {ok}/{len(results)} succeeded."
                self.log_queue.put(msg)
                self.after(0, lambda: self._busy(msg))
            except Exception as exc:  # noqa: BLE001
                self.log_queue.put(f"ERROR: {exc}")
                self.after(0, lambda: self._busy("Error"))

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def run_single(self):
        host = self.v_host.get().strip()
        if not host:
            messagebox.showwarning("Missing host", "Enter an IP or hostname.")
            return
        try:
            device = cb.Device(host=host, username=self.v_user.get().strip(),
                               password=self.v_pass.get(),
                               protocol=self.v_proto.get(),
                               family=self.v_family.get(),
                               secret=self.v_secret.get(),
                               port=self.v_port.get().strip() or None)
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return
        self._run([device])

    def browse_excel(self):
        path = filedialog.askopenfilename(
            title="Select device list",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if path:
            self.v_excel.set(path)

    def create_template(self):
        path = filedialog.asksaveasfilename(
            title="Save template as", defaultextension=".xlsx",
            initialfile="devices.xlsx",
            filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return
        try:
            cb.make_template(path)
            self.v_excel.set(path)
            messagebox.showinfo("Template created", f"Template written to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))

    def run_excel(self):
        path = self.v_excel.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("No file", "Choose a valid Excel file.")
            return
        logger = self._make_gui_logger()
        try:
            devices = cb.read_excel(path, logger)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read Excel", str(exc))
            return
        if not devices:
            messagebox.showwarning("Empty", "No valid devices found.")
            return
        self._run(devices)
