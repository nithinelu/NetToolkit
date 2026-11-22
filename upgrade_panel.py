#!/usr/bin/env python3
"""Upgrade tab for NetToolkit - TFTP push + Cisco IOS upgrade + MD5 verify."""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cisco_backup as cb
import tftp_server as tftp
import theme
import upgrade as up


class UpgradePanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.server: tftp.TftpServer | None = None
        self.conn = None
        self.worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._prog_state = {"pct": -1, "t": 0.0}
        self.local_md5_val = ""
        self._log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "logs")
        self._logfile = None
        self._logfile_path = ""
        self._build()
        self.after(150, self._drain)

    # -- helpers -----------------------------------------------------------
    def _v(self, key, default=""):
        setattr(self, key, tk.StringVar(value=str(default)))
        return getattr(self, key)

    def log(self, msg):
        self.log_queue.put(msg)

    def _qlog(self, msg):      # thread-safe logger passed to workers
        self.log_queue.put(msg)

    def _drain(self):
        fh = None
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.txt.configure(state="normal")
                self.txt.insert("end", line + "\n")
                self.txt.see("end")
                self.txt.configure(state="disabled")
                fh = fh or self._logfile_handle()
                if fh:
                    try:
                        fh.write(line + "\n")
                    except OSError:
                        pass
        except queue.Empty:
            pass
        if fh:
            try:
                fh.flush()
            except OSError:
                pass
        self.after(150, self._drain)

    def _busy(self) -> bool:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Busy", "Another operation is still running.\n\nUse the Stop "
                "button to cancel it.")
            return True
        return False

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _reset_progress(self):
        self._prog_state = {"pct": -1, "t": 0.0}
        self.after(0, lambda: (self.progress_bar.configure(value=0),
                               self.progress_var.set("")))

    def _progress_cb(self, name, sent, total):
        """Throttled progress update (<= ~3/sec, or on each new %)."""
        pct = int(sent * 100 / total) if total else 0
        now = time.time()
        st = self._prog_state
        if pct == st["pct"] and now - st["t"] < 0.3 and pct != 100:
            return
        st["pct"] = pct
        st["t"] = now
        txt = f"{pct}%  ({sent / 1048576:.1f}/{total / 1048576:.1f} MB)"
        self.after(0, lambda: (self.progress_bar.configure(value=pct),
                               self.progress_var.set(txt)))

    def _run(self, fn):
        if self._busy():
            return
        self._cancel.clear()

        def wrapped():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                self.log(f"Task ended with error: {exc}")
        self.worker = threading.Thread(target=wrapped, daemon=True)
        self.worker.start()

    def stop_task(self):
        """Cancel the running operation and free the panel."""
        if not (self.worker and self.worker.is_alive()):
            self.log("Nothing running.")
            return
        self._cancel.set()
        self.log("Stop requested - cancelling current operation ...")
        # disconnect to interrupt any blocking device I/O (unblocks the worker)
        c = self.conn
        if c is not None:
            self.conn = None
            threading.Thread(target=lambda: up.disconnect(c, self._qlog),
                             daemon=True).start()
            self.conn_btn.configure(text="Connect")
            self.conn_status.configure(text="not connected")

    # -- UI ----------------------------------------------------------------
    def _build(self):
        # ---- TFTP server ----
        srv = ttk.LabelFrame(self, text="Local TFTP server", padding=8)
        srv.pack(fill="x", pady=3)
        srv.columnconfigure(1, weight=1)
        ttk.Label(srv, text="Serve folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(srv, textvariable=self._v("tftp_root")).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(srv, text="Browse...", command=self._browse_root).grid(
            row=0, column=2)
        ttk.Label(srv, text="Bind IP:").grid(row=1, column=0, sticky="w")
        ips = tftp.local_ips()
        self._v("tftp_ip", ips[0])
        ttk.Combobox(srv, textvariable=self.tftp_ip, values=ips,
                     width=18).grid(row=1, column=1, sticky="w", padx=4)
        pf = ttk.Frame(srv)
        pf.grid(row=1, column=2)
        ttk.Label(pf, text="Port:").pack(side="left")
        ttk.Entry(pf, textvariable=self._v("tftp_port", "69"), width=6).pack(
            side="left")
        self.srv_btn = ttk.Button(srv, text="Start server",
                                  style="Accent.TButton",
                                  command=self.toggle_server)
        self.srv_btn.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.srv_status = ttk.Label(srv, text="stopped", style="Muted.TLabel")
        self.srv_status.grid(row=2, column=2, sticky="w", pady=(6, 0))

        # ---- Image file + MD5 ----
        img = ttk.LabelFrame(self, text="Firmware image & MD5", padding=8)
        img.pack(fill="x", pady=3)
        img.columnconfigure(1, weight=1)
        ttk.Label(img, text="Image file:").grid(row=0, column=0, sticky="w")
        ttk.Entry(img, textvariable=self._v("image_path")).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(img, text="Browse...", command=self._browse_image).grid(
            row=0, column=2)
        ttk.Label(img, text="Local MD5:").grid(row=1, column=0, sticky="w")
        ttk.Entry(img, textvariable=self._v("local_md5"), state="readonly").grid(
            row=1, column=1, sticky="ew", padx=4)
        ttk.Button(img, text="Compute", command=self.compute_md5).grid(
            row=1, column=2)
        ttk.Label(img, text="Expected MD5:").grid(row=2, column=0, sticky="w")
        ttk.Entry(img, textvariable=self._v("expected_md5")).grid(
            row=2, column=1, sticky="ew", padx=4)
        ttk.Label(img, text="(optional, from vendor)",
                  style="Muted.TLabel").grid(row=2, column=3, sticky="w")

        # ---- Device ----
        dev = ttk.LabelFrame(self, text="Target device", padding=8)
        dev.pack(fill="x", pady=3)
        for i in range(4):
            dev.columnconfigure(i * 2 + 1, weight=1)
        ttk.Label(dev, text="Host:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dev, textvariable=self._v("host")).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Label(dev, text="Protocol:").grid(row=0, column=2, sticky="w")
        ttk.Combobox(dev, textvariable=self._v("protocol", "ssh"),
                     values=["ssh", "telnet"], state="readonly",
                     width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(dev, text="Username:").grid(row=1, column=0, sticky="w")
        ttk.Entry(dev, textvariable=self._v("username")).grid(
            row=1, column=1, sticky="ew", padx=4)
        ttk.Label(dev, text="Password:").grid(row=1, column=2, sticky="w")
        ttk.Entry(dev, textvariable=self._v("password"), show="*").grid(
            row=1, column=3, sticky="ew", padx=4)
        ttk.Label(dev, text="Enable secret:").grid(row=2, column=0, sticky="w")
        ttk.Entry(dev, textvariable=self._v("secret"), show="*").grid(
            row=2, column=1, sticky="ew", padx=4)
        ttk.Label(dev, text="Filesystem:").grid(row=2, column=2, sticky="w")
        ttk.Combobox(dev, textvariable=self._v("dest_fs", "flash:"),
                     values=["flash:", "bootflash:", "disk0:", "flash0:"],
                     width=10).grid(row=2, column=3, sticky="w")
        ttk.Label(dev, text="Dest filename:").grid(row=3, column=0, sticky="w")
        ttk.Entry(dev, textvariable=self._v("dest_name")).grid(
            row=3, column=1, sticky="ew", padx=4)
        cf = ttk.Frame(dev)
        cf.grid(row=3, column=2, columnspan=2, sticky="e")
        self.conn_btn = ttk.Button(cf, text="Connect", command=self.toggle_conn)
        self.conn_btn.pack(side="left")
        self.conn_status = ttk.Label(cf, text="not connected",
                                     style="Muted.TLabel")
        self.conn_status.pack(side="left", padx=6)

        # ---- Actions ----
        mrow = ttk.Frame(self)
        mrow.pack(fill="x", pady=(6, 0))
        ttk.Label(mrow, text="Transfer method:").pack(side="left")
        ttk.Combobox(mrow, textvariable=self._v("method", "SCP (over SSH)"),
                     values=["SCP (over SSH)", "TFTP (server)"],
                     state="readonly", width=16).pack(side="left", padx=(4, 12))
        ttk.Label(mrow, style="Muted.TLabel",
                  text="SCP is reliable over the SSH session (no TFTP server / "
                       "firewall ports needed).").pack(side="left")
        ttk.Button(mrow, text="STOP", command=self.stop_task).pack(side="right")

        act = ttk.Frame(self)
        act.pack(fill="x", pady=(4, 0))
        ttk.Button(act, text="1. Upload image", style="Accent.TButton",
                   command=self.do_upload).pack(side="left", padx=2)
        ttk.Button(act, text="2. Verify MD5 on device",
                   command=self.do_verify).pack(side="left", padx=2)
        ttk.Button(act, text="3. Set boot && save",
                   command=self.do_setboot).pack(side="left", padx=2)
        ttk.Button(act, text="4. Reload device",
                   command=self.do_reload).pack(side="left", padx=2)
        self.clear_boot = tk.BooleanVar(value=True)
        ttk.Checkbutton(act, text="clear old boot entries",
                        variable=self.clear_boot).pack(side="left", padx=(12, 0))

        # ---- Upload progress ----
        prog = ttk.Frame(self)
        prog.pack(fill="x", pady=(6, 0))
        self.progress_bar = ttk.Progressbar(prog, orient="horizontal",
                                            mode="determinate", maximum=100)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_var = tk.StringVar(value="")
        ttk.Label(prog, textvariable=self.progress_var, style="Muted.TLabel",
                  width=28, anchor="w").pack(side="left", padx=(8, 0))

        # ---- Batch from Excel inventory ----
        batch = ttk.LabelFrame(
            self, text="Batch upgrade from Excel inventory", padding=8)
        batch.pack(fill="x", pady=(6, 0))
        batch.columnconfigure(1, weight=1)
        ttk.Label(batch, text="Inventory:").grid(row=0, column=0, sticky="w")
        ttk.Entry(batch, textvariable=self._v("inv_path")).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(batch, text="Browse...", command=self._browse_inv).grid(
            row=0, column=2)
        ttk.Button(batch, text="Create template...",
                   command=self._inv_template).grid(row=0, column=3, padx=(4, 0))
        steps = ttk.Frame(batch)
        steps.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.b_upload = tk.BooleanVar(value=True)
        self.b_verify = tk.BooleanVar(value=True)
        self.b_setboot = tk.BooleanVar(value=False)
        self.b_reload = tk.BooleanVar(value=False)
        ttk.Label(steps, text="Steps:").pack(side="left")
        ttk.Checkbutton(steps, text="Upload", variable=self.b_upload).pack(
            side="left", padx=4)
        ttk.Checkbutton(steps, text="Verify MD5", variable=self.b_verify).pack(
            side="left", padx=4)
        ttk.Checkbutton(steps, text="Set boot & save",
                        variable=self.b_setboot).pack(side="left", padx=4)
        ttk.Checkbutton(steps, text="Allow reload", variable=self.b_reload).pack(
            side="left", padx=4)
        ttk.Button(batch, text="Run batch upgrade", style="Accent.TButton",
                   command=self.do_batch).grid(row=2, column=1, sticky="w",
                                               pady=(6, 0))
        ttk.Label(batch, style="Muted.TLabel",
                  text="Images must be in the TFTP serve folder; the server "
                       "must be running. Set-boot/reload only run when MD5 "
                       "matches.").grid(row=3, column=0, columnspan=4,
                                        sticky="w", pady=(4, 0))

        # ---- Log (with scrollbars; also written to logs\upgrade_*.log) ----
        logbar = ttk.Frame(self)
        logbar.pack(fill="x", pady=(8, 0))
        ttk.Label(logbar, text="Log:").pack(side="left")
        ttk.Button(logbar, text="Clear view",
                   command=self.clear_log).pack(side="right")
        ttk.Button(logbar, text="Save log...",
                   command=self.save_log).pack(side="right", padx=4)
        ttk.Button(logbar, text="Open logs folder",
                   command=self.open_logs).pack(side="right")
        self.log_file_lbl = ttk.Label(logbar, style="Muted.TLabel", text="")
        self.log_file_lbl.pack(side="left", padx=10)

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(2, 0))
        yscroll = ttk.Scrollbar(wrap, orient="vertical")
        xscroll = ttk.Scrollbar(wrap, orient="horizontal")
        self.txt = tk.Text(wrap, height=14, wrap="none",
                           background=theme.CONSOLE_BG,
                           foreground=theme.CONSOLE_FG, font=theme.MONO_FONT,
                           relief="flat", borderwidth=0, padx=8, pady=6,
                           yscrollcommand=yscroll.set,
                           xscrollcommand=xscroll.set)
        yscroll.configure(command=self.txt.yview)
        xscroll.configure(command=self.txt.xview)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.configure(state="disabled")

    # -- logging to file ---------------------------------------------------
    def _logfile_handle(self):
        """Open (once) a per-session log file under the tool's logs folder."""
        if self._logfile is not None:
            return self._logfile
        try:
            import datetime
            os.makedirs(self._log_dir, exist_ok=True)
            path = os.path.join(
                self._log_dir,
                f"upgrade_{datetime.datetime.now():%Y%m%d_%H%M%S}.log")
            self._logfile = open(path, "a", encoding="utf-8")
            self._logfile_path = path
            self.after(0, lambda: self.log_file_lbl.configure(
                text="saving to " + os.path.basename(path)))
        except OSError:
            self._logfile = None
        return self._logfile

    def clear_log(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def save_log(self):
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Save log", "The log is empty.")
            return
        path = filedialog.asksaveasfilename(
            title="Save log", defaultextension=".log",
            initialfile="upgrade.log",
            filetypes=[("Log", "*.log *.txt"), ("All files", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            messagebox.showinfo("Saved", f"Log saved to:\n{path}")

    def open_logs(self):
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            os.startfile(self._log_dir)  # noqa: S606 (Windows)
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo("Logs folder", f"{self._log_dir}\n\n{exc}")

    # -- TFTP server -------------------------------------------------------
    def _browse_root(self):
        d = filedialog.askdirectory(title="Folder to serve over TFTP")
        if d:
            self.tftp_root.set(d)

    def toggle_server(self):
        if self.server and self.server.running:
            self.server.stop()
            self.server = None
            self.srv_btn.configure(text="Start server")
            self.srv_status.configure(text="stopped")
            return
        root = self.tftp_root.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("Folder", "Choose a valid folder to serve.")
            return
        try:
            port = int(self.tftp_port.get())
        except ValueError:
            messagebox.showwarning("Port", "Port must be a number.")
            return
        try:
            self.server = tftp.TftpServer(root=root, bind_ip=self.tftp_ip.get(),
                                          port=port, log=self._qlog,
                                          progress=self._progress_cb)
            self.server.start()
        except OSError as exc:
            messagebox.showerror(
                "TFTP server",
                f"Could not start on port {port}:\n{exc}\n\nPort 69 may be in "
                "use or blocked by the firewall; try a higher port and set the "
                "device copy to use it.")
            self.server = None
            return
        self.srv_btn.configure(text="Stop server")
        self.srv_status.configure(text=f"running on {self.tftp_ip.get()}:{port}")

    # -- image / md5 -------------------------------------------------------
    def _browse_image(self):
        f = filedialog.askopenfilename(
            title="Select firmware image",
            filetypes=[("Images", "*.bin *.SPA *.spa *.tar *.pkg *.conf"),
                       ("All files", "*.*")])
        if not f:
            return
        self.image_path.set(f)
        self.dest_name.set(os.path.basename(f))
        if not self.tftp_root.get().strip():
            self.tftp_root.set(os.path.dirname(f))
        self.compute_md5()

    def compute_md5(self):
        path = self.image_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Image", "Choose a valid image file.")
            return

        def task():
            self.log(f"Computing local MD5 of {os.path.basename(path)} ...")
            try:
                digest = up.local_md5(path)
            except OSError as exc:
                self.log(f"MD5 error: {exc}")
                return
            self.local_md5_val = digest
            self.after(0, lambda: self.local_md5.set(digest))
            self.log(f"Local MD5: {digest}")
            exp = self.expected_md5.get().strip().lower()
            if exp:
                ok = exp == digest
                self.log("Expected-MD5 check: " + ("MATCH" if ok else "MISMATCH"))
        self._run(task)

    # -- device connection -------------------------------------------------
    def _device(self):
        return cb.Device(host=self.host.get().strip(),
                         username=self.username.get().strip(),
                         password=self.password.get(),
                         protocol=self.protocol.get(),
                         family="ios", secret=self.secret.get())

    def toggle_conn(self):
        if self.conn is not None:
            up.disconnect(self.conn, self._qlog)
            self.conn = None
            self.conn_btn.configure(text="Connect")
            self.conn_status.configure(text="not connected")
            return
        if not self.host.get().strip():
            messagebox.showwarning("Host", "Enter the device host/IP.")
            return

        def task():
            try:
                dev = self._device()
                self.conn = up.connect(dev, self._qlog)
            except Exception as exc:  # noqa: BLE001
                self.log(f"Connect failed: {exc}")
                self.after(0, lambda: self.conn_status.configure(
                    text="connect failed"))
                return
            self.after(0, lambda: (self.conn_btn.configure(text="Disconnect"),
                                   self.conn_status.configure(text="connected")))
        self._run(task)

    def _need_conn(self) -> bool:
        if self.conn is None:
            messagebox.showwarning("Not connected",
                                   "Connect to the device first.")
            return False
        return True

    # -- actions -----------------------------------------------------------
    def do_upload(self):
        if not self._need_conn():
            return
        use_scp = self.method.get().startswith("SCP")
        img = self.image_path.get().strip()
        fname = self.dest_name.get().strip() or os.path.basename(img)
        if not fname:
            messagebox.showwarning("File", "Select an image / dest filename.")
            return

        if use_scp:
            if not img or not os.path.isfile(img):
                messagebox.showwarning(
                    "Image", "SCP needs the local image file - pick it in the "
                    "'Firmware image' section.")
                return

            self._reset_progress()

            def task():
                self.log("=== Upload via SCP ===")
                up.scp_copy_to_device(self.conn, img, dest_name=fname,
                                      dest_fs=self.dest_fs.get(),
                                      log=self._qlog,
                                      progress=self._progress_cb)
            self._run(task)
            return

        # TFTP
        if not (self.server and self.server.running):
            if not messagebox.askyesno(
                    "TFTP server", "The local TFTP server is not running. "
                    "The device won't be able to pull the image. Continue "
                    "anyway?"):
                return

        self._reset_progress()

        def task():
            self.log("=== Upload via TFTP ===")
            up.tftp_copy_to_device(self.conn, self.tftp_ip.get(), fname,
                                   dest_fs=self.dest_fs.get(), dest_name=fname,
                                   log=self._qlog, cancel=self.cancelled)
        self._run(task)

    def do_verify(self):
        if not self._need_conn():
            return
        fname = self.dest_name.get().strip()
        if not fname:
            messagebox.showwarning("File", "Enter the destination filename.")
            return

        def task():
            self.log("=== Verify MD5 on device ===")
            digest, _ = up.verify_md5_on_device(
                self.conn, fname, dest_fs=self.dest_fs.get(), log=self._qlog)
            local = self.local_md5_val or self.local_md5.get().strip().lower()
            if digest and local:
                ok = digest == local
                self.log("")
                self.log("  Local  MD5: " + local)
                self.log("  Device MD5: " + digest)
                self.log("  RESULT: " + ("MATCH - image intact"
                                         if ok else "MISMATCH - do NOT boot!"))
                self.after(0, lambda: (messagebox.showinfo if ok
                                       else messagebox.showerror)(
                    "MD5 verify",
                    "MATCH - the image on the device is intact." if ok else
                    "MISMATCH - the uploaded image is corrupt. Do not boot it."))
            elif digest and not local:
                self.log("Device MD5 = " + digest +
                         " (compute the local MD5 to compare).")
        self._run(task)

    def do_setboot(self):
        if not self._need_conn():
            return
        fname = self.dest_name.get().strip()
        if not fname:
            return
        if not messagebox.askyesno(
                "Set boot", f"Set the device to boot from "
                f"{self.dest_fs.get()}{fname} and save the config?"):
            return

        def task():
            self.log("=== Set boot system & save ===")
            out = up.set_boot_system(self.conn, fname, dest_fs=self.dest_fs.get(),
                                     clear_existing=self.clear_boot.get(),
                                     save=True, log=self._qlog)
            self.log(out)
        self._run(task)

    def do_reload(self):
        if not self._need_conn():
            return
        if not messagebox.askyesno(
                "Reload device", "This will REBOOT the device now and drop the "
                "connection. Make sure the new image is uploaded, MD5-verified "
                "and the boot variable is set.\n\nProceed with reload?",
                icon="warning"):
            return

        def task():
            self.log("=== Reload ===")
            try:
                up.reload_device(self.conn, save_first=False, log=self._qlog)
            except Exception as exc:  # noqa: BLE001
                self.log(f"(connection dropped during reload: {exc})")
            up.disconnect(self.conn, self._qlog)
            self.conn = None
            self.after(0, lambda: (self.conn_btn.configure(text="Connect"),
                                   self.conn_status.configure(
                                       text="rebooting...")))
        self._run(task)

    # -- batch (Excel inventory) -------------------------------------------
    def _browse_inv(self):
        f = filedialog.askopenfilename(
            title="Select upgrade inventory",
            filetypes=[("Excel", "*.xlsx"), ("All files", "*.*")])
        if f:
            self.inv_path.set(f)

    def _inv_template(self):
        path = filedialog.asksaveasfilename(
            title="Save inventory template", defaultextension=".xlsx",
            initialfile="upgrade_inventory.xlsx",
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            up.make_inventory_template(path)
            self.inv_path.set(path)
            messagebox.showinfo("Template", f"Inventory template written to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))

    def do_batch(self):
        if self._busy():
            return
        path = self.inv_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Inventory", "Choose a valid Excel inventory.")
            return
        use_scp = self.method.get().startswith("SCP")
        if not use_scp and not (self.server and self.server.running):
            messagebox.showwarning(
                "TFTP server", "Start the local TFTP server first - the "
                "devices pull the image from it. (Or switch the transfer "
                "method to SCP.)")
            return
        try:
            rows = up.read_inventory(path, self._qlog)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Inventory", str(exc))
            return
        if not rows:
            messagebox.showwarning("Inventory", "No devices found.")
            return
        root = self.tftp_root.get().strip()
        steps = {"upload": self.b_upload.get(), "verify": self.b_verify.get(),
                 "set_boot": self.b_setboot.get(),
                 "allow_reload": self.b_reload.get(),
                 "clear_boot": self.clear_boot.get(),
                 "method": "scp" if self.method.get().startswith("SCP")
                 else "tftp"}
        if steps["allow_reload"]:
            if not messagebox.askyesno(
                    "Reload enabled",
                    f"'Allow reload' is ON. Devices whose inventory row has "
                    f"reload=yes WILL be rebooted after a successful, "
                    f"MD5-verified upload.\n\nRun the batch on {len(rows)} "
                    f"device(s)?", icon="warning"):
                return
        elif not messagebox.askyesno(
                "Run batch", f"Run the selected steps on {len(rows)} device(s)?"):
            return

        def task():
            self.log(f"\n######## BATCH UPGRADE - {len(rows)} device(s) ########")
            up.run_batch(rows, self.tftp_ip.get(), root, steps, self._qlog,
                         cancel=self.cancelled, progress=self._progress_cb)
        self._run(task)
        self._reset_progress()
