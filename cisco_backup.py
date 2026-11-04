#!/usr/bin/env python3
"""
Cisco Device Backup - core logic
================================

Backs up the running configuration of Cisco devices over SSH or Telnet,
for a single device or a batch listed in an Excel file. Built on Netmiko.

This module is used by the CiscoToolkit GUI; it also has a small CLI::

    python cisco_backup.py --host 192.168.1.1 --username admin
    python cisco_backup.py --excel devices.xlsx --show-tech
    python cisco_backup.py --make-template devices.xlsx
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
LOG_DIR = os.path.join(BASE_DIR, "logs")

CONFIG_COMMAND = "show running-config"
TECH_COMMAND = "show tech-support"
TECH_READ_TIMEOUT = 600  # seconds

DEVICE_TYPE_MAP = {
    ("ssh", "ios"): "cisco_ios",
    ("ssh", "xe"): "cisco_xe",
    ("ssh", "nxos"): "cisco_nxos",
    ("ssh", "asa"): "cisco_asa",
    # Netmiko only ships a generic Cisco IOS telnet driver; it works for the
    # IOS/IOS-XE CLI. NX-OS/ASA over telnet are uncommon and fall back to it.
    ("telnet", "ios"): "cisco_ios_telnet",
    ("telnet", "xe"): "cisco_ios_telnet",
    ("telnet", "nxos"): "cisco_ios_telnet",
    ("telnet", "asa"): "cisco_ios_telnet",
}

DEFAULT_PORTS = {"ssh": 22, "telnet": 23}


@dataclass
class Device:
    host: str
    username: str
    password: str
    protocol: str = "ssh"
    family: str = "ios"
    secret: str = ""
    port: Optional[int] = None
    name: str = ""

    def __post_init__(self):
        self.protocol = (self.protocol or "ssh").strip().lower()
        self.family = (self.family or "ios").strip().lower()
        if self.protocol not in ("ssh", "telnet"):
            raise ValueError(
                f"Unknown protocol '{self.protocol}' for host {self.host} "
                "(expected 'ssh' or 'telnet')")
        if self.port in (None, "", 0):
            self.port = DEFAULT_PORTS[self.protocol]
        else:
            self.port = int(self.port)
        if not self.name:
            self.name = self.host

    def netmiko_device_type(self) -> str:
        key = (self.protocol, self.family)
        if key not in DEVICE_TYPE_MAP:
            raise ValueError(
                f"Unsupported protocol/family combination {key} for {self.host}")
        return DEVICE_TYPE_MAP[key]


@dataclass
class BackupResult:
    device: Device
    success: bool
    path: str = ""
    tech_path: str = ""
    error: str = ""


def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"backup_{datetime.now():%Y%m%d_%H%M%S}.log")
    logger = logging.getLogger("cisco_backup")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logger.info("Logging to %s", log_path)
    return logger


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in name)


def _save_output(device: Device, command: str, output: str,
                 suffix: str, ext: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    filename = f"{_safe_name(device.name)}{suffix}_{stamp}.{ext}"
    path = os.path.join(BACKUP_DIR, filename)
    header = (
        f"! Backup of {device.name} ({device.host})\n"
        f"! Protocol: {device.protocol}  Device type: "
        f"{device.netmiko_device_type()}\n"
        f"! Taken: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"! Command: {command}\n!\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(output)
    return path


def backup_device(device: Device, logger: logging.Logger,
                  config_command: str = CONFIG_COMMAND,
                  capture_tech: bool = False,
                  tech_command: str = TECH_COMMAND,
                  tech_timeout: int = TECH_READ_TIMEOUT) -> BackupResult:
    from netmiko import ConnectHandler
    from netmiko.exceptions import (NetmikoAuthenticationException,
                                    NetmikoTimeoutException)

    conn_params = {
        "device_type": device.netmiko_device_type(),
        "host": device.host,
        "username": device.username,
        "password": device.password,
        "port": device.port,
        "secret": device.secret,
        "fast_cli": False,
    }
    logger.info("Connecting to %s (%s, port %s) ...",
                device.host, device.protocol, device.port)
    try:
        with ConnectHandler(**conn_params) as conn:
            if device.secret:
                try:
                    conn.enable()
                except Exception as exc:
                    logger.warning("enable() failed on %s: %s", device.host, exc)
            prompt = conn.find_prompt()
            logger.info("Connected to %s (prompt: %s)", device.host, prompt)
            output = conn.send_command(config_command, read_timeout=120)
            path = _save_output(device, config_command, output, "", "cfg")
            logger.info("SUCCESS: %s -> %s", device.host, path)
            tech_path = ""
            if capture_tech:
                logger.info("Capturing '%s' on %s (this can take a while) ...",
                            tech_command, device.host)
                tech_output = conn.send_command(tech_command,
                                                read_timeout=tech_timeout)
                tech_path = _save_output(device, tech_command, tech_output,
                                         "_tech", "txt")
                logger.info("SUCCESS: %s -> %s", device.host, tech_path)
        return BackupResult(device=device, success=True, path=path,
                            tech_path=tech_path)
    except NetmikoAuthenticationException as exc:
        msg = f"Authentication failed: {exc}"
    except NetmikoTimeoutException as exc:
        msg = f"Connection timed out: {exc}"
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
    logger.error("FAILED:  %s -> %s", device.host, msg)
    return BackupResult(device=device, success=False, error=msg)


def backup_many(devices: List[Device], logger: logging.Logger,
                config_command: str = CONFIG_COMMAND,
                capture_tech: bool = False,
                tech_timeout: int = TECH_READ_TIMEOUT) -> List[BackupResult]:
    results = []
    total = len(devices)
    for i, device in enumerate(devices, 1):
        logger.info("--- [%d/%d] %s ---", i, total, device.host)
        results.append(backup_device(device, logger, config_command,
                                     capture_tech, tech_timeout=tech_timeout))
    return results


EXCEL_COLUMNS = ["host", "protocol", "family", "username",
                 "password", "secret", "port", "name"]


def make_template(path: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws.title = "devices"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    notes = {
        "host": "Required. IP address or hostname.",
        "protocol": "ssh or telnet (default ssh).",
        "family": "ios, xe, nxos or asa (default ios).",
        "username": "Login username.",
        "password": "Login password.",
        "secret": "Enable secret. Leave blank if not needed.",
        "port": "Optional. Defaults: ssh=22, telnet=23.",
        "name": "Optional friendly name for the backup file.",
    }
    for col, header in enumerate(EXCEL_COLUMNS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.comment = Comment(notes[header], "Cisco Backup Tool")
        ws.column_dimensions[cell.column_letter].width = max(14, len(header) + 4)
    ws.append(["192.168.1.1", "ssh", "ios", "admin", "password", "", 22, "core-sw"])
    ws.append(["10.0.0.10", "telnet", "ios", "admin", "password", "enablepw", 23, "edge-rtr"])
    ws.freeze_panes = "A2"
    wb.save(path)


def read_excel(path: str, logger: logging.Logger) -> List[Device]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header = [str(h).strip().lower() if h is not None else ""
                  for h in next(rows)]
    except StopIteration:
        raise ValueError("Excel file is empty")
    missing = [c for c in ("host", "username", "password") if c not in header]
    if missing:
        raise ValueError(
            f"Excel file is missing required column(s): {', '.join(missing)}. "
            f"Found columns: {', '.join(header)}")
    idx = {name: header.index(name) for name in header}
    devices: List[Device] = []

    def get(row, col):
        if col in idx and idx[col] < len(row):
            val = row[idx[col]]
            return "" if val is None else str(val).strip()
        return ""

    for line_no, row in enumerate(rows, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        host = get(row, "host")
        if not host:
            logger.warning("Row %d skipped: no host", line_no)
            continue
        try:
            devices.append(Device(
                host=host, username=get(row, "username"),
                password=get(row, "password"),
                protocol=get(row, "protocol") or "ssh",
                family=get(row, "family") or "ios",
                secret=get(row, "secret"),
                port=get(row, "port") or None, name=get(row, "name")))
        except ValueError as exc:
            logger.error("Row %d skipped: %s", line_no, exc)
    wb.close()
    return devices


def _cli(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Back up Cisco device configs.")
    p.add_argument("--host")
    p.add_argument("--excel")
    p.add_argument("--make-template", metavar="PATH")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--secret", default="")
    p.add_argument("--protocol", choices=["ssh", "telnet"], default="ssh")
    p.add_argument("--family", choices=["ios", "xe", "nxos", "asa"], default="ios")
    p.add_argument("--port", type=int)
    p.add_argument("--name")
    p.add_argument("--command", default=CONFIG_COMMAND)
    p.add_argument("--show-tech", action="store_true")
    p.add_argument("--tech-timeout", type=int, default=TECH_READ_TIMEOUT)
    args = p.parse_args(argv)

    if args.make_template:
        make_template(args.make_template)
        print(f"Template written to {args.make_template}")
        return 0
    if not args.host and not args.excel:
        p.error("Provide --host, --excel, or --make-template.")

    logger = setup_logging()
    if args.excel:
        if not os.path.isfile(args.excel):
            logger.error("Excel file not found: %s", args.excel)
            return 2
        devices = read_excel(args.excel, logger)
        if not devices:
            logger.error("No valid devices found in %s", args.excel)
            return 2
    else:
        username = args.username or input("Username: ").strip()
        password = args.password or getpass.getpass("Password: ")
        devices = [Device(host=args.host, username=username, password=password,
                          protocol=args.protocol, family=args.family,
                          secret=args.secret, port=args.port,
                          name=args.name or "")]
    results = backup_many(devices, logger, args.command, args.show_tech,
                          tech_timeout=args.tech_timeout)
    ok = [r for r in results if r.success]
    bad = [r for r in results if not r.success]
    logger.info("=" * 60)
    logger.info("Backup complete: %d succeeded, %d failed", len(ok), len(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(_cli())
