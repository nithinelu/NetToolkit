#!/usr/bin/env python3
"""
Device firmware-upgrade helpers for NetToolkit (Cisco IOS/IOS-XE).

Drives the interactive `copy tftp:` dialog, verifies image integrity with
`verify /md5`, sets the boot variable, and reloads - all over an existing
Netmiko SSH/Telnet session. Pairs with the built-in TFTP server (tftp_server.py).

These functions talk to real devices and change/boot flash. Use with care and
test on one device first.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Callable, Optional, Tuple

Logger = Callable[[str], None]


def local_md5(path: str, log: Optional[Logger] = None) -> str:
    """MD5 of a local file (chunked)."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if log:
        log(f"Local MD5 ({path}): {digest}")
    return digest


def connect(device, log: Optional[Logger] = None):
    """Open a Netmiko connection from a cisco_backup.Device."""
    from netmiko import ConnectHandler
    params = {
        "device_type": device.netmiko_device_type(),
        "host": device.host,
        "username": device.username,
        "password": device.password,
        "port": device.port,
        "secret": device.secret,
        "fast_cli": False,
    }
    if log:
        log(f"Connecting to {device.host} ({device.protocol}) ...")
    conn = ConnectHandler(**params)
    if device.secret:
        try:
            conn.enable()
        except Exception as exc:  # noqa: BLE001
            if log:
                log(f"enable() failed: {exc}")
    if log:
        log(f"Connected: {conn.find_prompt()}")
    return conn


# Prompt substrings -> response (checked in order; specific before generic).
_COPY_ANSWERS = [
    ("address or name of remote host", "__TFTP_IP__"),
    ("source filename", "__FILENAME__"),
    ("destination filename", ""),            # accept default (Enter)
    ("erase flash", "n"),                    # never erase before copy
    ("do you want to over write", "y"),
    ("over write", "y"),
    ("overwrite", "y"),
    ("[confirm]", ""),                       # Enter confirms
]


def tftp_copy_to_device(conn, tftp_ip: str, filename: str,
                        dest_fs: str = "flash:", dest_name: Optional[str] = None,
                        log: Optional[Logger] = None,
                        read_timeout: int = 1800) -> str:
    """Pull `filename` from the TFTP server at `tftp_ip` into `dest_fs`.

    Drives the interactive IOS copy dialog. Returns the full session text.
    """
    log = log or (lambda m: None)
    dest_name = dest_name or filename
    answers = [(k, v.replace("__TFTP_IP__", tftp_ip)
                   .replace("__FILENAME__", filename)) for k, v in _COPY_ANSWERS]

    cmd = f"copy tftp://{tftp_ip}/{filename} {dest_fs}{dest_name}"
    log(f"> {cmd}")
    out = conn.send_command_timing(cmd, strip_prompt=False,
                                   strip_command=False, read_timeout=60)
    full = out
    start = time.time()
    idle = 0
    while time.time() - start < read_timeout:
        low = out.lower()
        if any(s in low for s in ("bytes copied", "[ok -", "[ok]")):
            log("Transfer complete.")
            break
        if "%error" in low or "error opening" in low or "timed out" in low:
            log("Transfer error (see log).")
            break
        responded = False
        for key, resp in answers:
            if key in low:
                shown = resp if resp else "<Enter>"
                log(f"  prompt: '{key}' -> {shown}")
                out = conn.send_command_timing(resp, strip_prompt=False,
                                               strip_command=False,
                                               read_timeout=read_timeout)
                full += out
                responded = True
                break
        if not responded:
            out = conn.send_command_timing("", strip_prompt=False,
                                           strip_command=False, read_timeout=30)
            full += out
            if not out.strip():
                idle += 1
                if idle >= 2:
                    break
            else:
                idle = 0
    return full


_MD5_RE = re.compile(r"=\s*([0-9a-fA-F]{32})")
_HEX32_RE = re.compile(r"\b([0-9a-fA-F]{32})\b")


def verify_md5_on_device(conn, filename: str, dest_fs: str = "flash:",
                         log: Optional[Logger] = None,
                         read_timeout: int = 900) -> Tuple[Optional[str], str]:
    """Run `verify /md5` on the device and return (md5, raw_output)."""
    log = log or (lambda m: None)
    cmd = f"verify /md5 {dest_fs}{filename}"
    log(f"> {cmd}  (this can take a minute)")
    out = conn.send_command(cmd, read_timeout=read_timeout)
    m = _MD5_RE.search(out) or _HEX32_RE.search(out)
    digest = m.group(1).lower() if m else None
    log(f"Device MD5: {digest or '(not found in output)'}")
    return digest, out


def set_boot_system(conn, filename: str, dest_fs: str = "flash:",
                    clear_existing: bool = True, save: bool = True,
                    log: Optional[Logger] = None) -> str:
    """Set the boot variable to the new image (optionally clearing old ones)."""
    log = log or (lambda m: None)
    cmds = []
    if clear_existing:
        cmds.append("no boot system")
    cmds.append(f"boot system {dest_fs}{filename}")
    log("Setting boot system: " + "; ".join(cmds))
    out = conn.send_config_set(cmds)
    if save:
        log("Saving configuration (write memory) ...")
        out += "\n" + conn.save_config()
    return out


def reload_device(conn, save_first: bool = False,
                  log: Optional[Logger] = None) -> str:
    """Reload the device. The session drops as it reboots."""
    log = log or (lambda m: None)
    log("> reload")
    out = conn.send_command_timing("reload", strip_prompt=False,
                                   strip_command=False, read_timeout=30)
    full = out
    for _ in range(6):
        low = out.lower()
        if "save" in low and ("yes/no" in low or "[yes/no]" in low):
            resp = "yes" if save_first else "no"
            log(f"  'Save?' -> {resp}")
            out = conn.send_command_timing(resp, strip_prompt=False,
                                           strip_command=False, read_timeout=30)
        elif "proceed with reload" in low or "[confirm]" in low:
            log("  'Proceed with reload?' -> <Enter>")
            try:
                conn.write_channel("\n")
            except Exception:  # noqa: BLE001
                pass
            log("Reload issued; device is rebooting.")
            break
        else:
            out = conn.send_command_timing("", strip_prompt=False,
                                           strip_command=False, read_timeout=15)
        full += out
    return full


def disconnect(conn, log: Optional[Logger] = None):
    try:
        conn.disconnect()
    except Exception:  # noqa: BLE001
        pass
    if log:
        log("Disconnected.")
