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
import os
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


# =====================================================================
# Excel inventory (batch upgrade of many devices)
# =====================================================================
INVENTORY_COLUMNS = ["host", "protocol", "username", "password", "secret",
                     "image", "dest_fs", "dest_name", "expected_md5",
                     "set_boot", "reload"]


def make_inventory_template(path: str) -> None:
    """Write a blank Excel inventory template for batch upgrades."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws.title = "upgrade"
    fill = PatternFill("solid", fgColor="1F4E78")
    font = Font(color="FFFFFF", bold=True)
    notes = {
        "host": "Required. Device IP or hostname.",
        "protocol": "ssh or telnet (default ssh).",
        "username": "Login username.",
        "password": "Login password.",
        "secret": "Enable secret (optional).",
        "image": "Image filename to push. MUST exist in the TFTP serve folder.",
        "dest_fs": "Destination filesystem (default flash:).",
        "dest_name": "Destination filename (default = image).",
        "expected_md5": "Optional vendor MD5 to verify against (else the local "
                        "file's MD5 is used).",
        "set_boot": "yes/no - set boot variable + save when MD5 matches.",
        "reload": "yes/no - reload after boot is set (only if 'Allow reload' "
                  "is also enabled in the app).",
    }
    for col, header in enumerate(INVENTORY_COLUMNS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = fill
        cell.font = font
        cell.comment = Comment(notes[header], "NetToolkit")
        ws.column_dimensions[cell.column_letter].width = max(12, len(header) + 4)
    ws.append(["10.0.0.11", "ssh", "admin", "password", "", "c2900-universalk9.SPA.bin",
               "flash:", "", "", "yes", "no"])
    ws.append(["10.0.0.12", "ssh", "admin", "password", "", "c2900-universalk9.SPA.bin",
               "flash:", "", "", "yes", "no"])
    ws.freeze_panes = "A2"
    wb.save(path)


def read_inventory(path: str, log: Optional[Logger] = None) -> list:
    """Read upgrade rows from an Excel file (first row = headers)."""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header = [str(h).strip().lower() if h is not None else ""
                  for h in next(rows)]
    except StopIteration:
        raise ValueError("Excel file is empty")
    missing = [c for c in ("host", "username", "password", "image")
               if c not in header]
    if missing:
        raise ValueError("Inventory missing required column(s): "
                         + ", ".join(missing))
    idx = {name: header.index(name) for name in header}

    def get(row, col):
        if col in idx and idx[col] < len(row):
            v = row[idx[col]]
            return "" if v is None else str(v).strip()
        return ""

    out = []
    for n, row in enumerate(rows, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        host = get(row, "host")
        if not host:
            continue
        out.append({c: get(row, c) for c in INVENTORY_COLUMNS})
    wb.close()
    if log:
        log(f"Loaded {len(out)} device(s) from {path}")
    return out


def _yes(val: str) -> bool:
    return str(val).strip().lower() in ("y", "yes", "true", "1")


def upgrade_one(row: dict, tftp_ip: str, tftp_root: str, steps: dict,
                md5_cache: dict, log: Logger) -> dict:
    """Run the selected upgrade steps on one device; return a result dict."""
    import cisco_backup as cb
    host = row["host"]
    res = {"host": host, "success": False, "local_md5": "", "device_md5": "",
           "match": None, "error": "", "actions": []}
    image = row.get("image", "")
    dest_fs = row.get("dest_fs") or "flash:"
    dest_name = row.get("dest_name") or image
    log(f"===== {host} ({image}) =====")

    # local MD5 of the served image (cached per filename)
    img_path = os.path.join(tftp_root, os.path.basename(image)) if image else ""
    local = md5_cache.get(img_path)
    if image and local is None and os.path.isfile(img_path):
        local = local_md5(img_path)
        md5_cache[img_path] = local
    res["local_md5"] = local or ""

    conn = None
    try:
        dev = cb.Device(host=host, username=row.get("username", ""),
                        password=row.get("password", ""),
                        protocol=row.get("protocol") or "ssh", family="ios",
                        secret=row.get("secret", ""))
        conn = connect(dev, log)

        if steps.get("upload") and image:
            tftp_copy_to_device(conn, tftp_ip, image, dest_fs=dest_fs,
                                dest_name=dest_name, log=log)
            res["actions"].append("upload")

        if steps.get("verify"):
            dmd5, _ = verify_md5_on_device(conn, dest_name, dest_fs=dest_fs,
                                           log=log)
            res["device_md5"] = dmd5 or ""
            expected = (row.get("expected_md5") or local or "").lower()
            if dmd5 and expected:
                res["match"] = (dmd5 == expected)
                log(f"  MD5 {'MATCH' if res['match'] else 'MISMATCH'} "
                    f"(device={dmd5}, expected={expected})")
            res["actions"].append("verify")

        ok_to_change = res["match"] is not False  # True or unknown
        if steps.get("set_boot") and _yes(row.get("set_boot")) and ok_to_change:
            set_boot_system(conn, dest_name, dest_fs=dest_fs,
                            clear_existing=steps.get("clear_boot", True),
                            save=True, log=log)
            res["actions"].append("set_boot")
            if (steps.get("allow_reload") and _yes(row.get("reload"))
                    and res["match"]):
                reload_device(conn, save_first=False, log=log)
                res["actions"].append("reload")
        elif steps.get("set_boot") and res["match"] is False:
            log("  Skipping set-boot/reload: MD5 mismatch.")

        res["success"] = True
    except Exception as exc:  # noqa: BLE001
        res["error"] = f"{type(exc).__name__}: {exc}"
        log(f"  ERROR: {res['error']}")
    finally:
        if conn is not None and "reload" not in res["actions"]:
            disconnect(conn, log)
    return res


def run_batch(rows: list, tftp_ip: str, tftp_root: str, steps: dict,
              log: Logger) -> list:
    """Run upgrade_one across all rows sequentially; return result list."""
    md5_cache: dict = {}
    results = []
    total = len(rows)
    for i, row in enumerate(rows, 1):
        log(f"\n--- [{i}/{total}] ---")
        results.append(upgrade_one(row, tftp_ip, tftp_root, steps, md5_cache,
                                   log))
    ok = sum(1 for r in results if r["success"] and r["match"] is not False)
    log("\n" + "=" * 50)
    log(f"Batch complete: {ok}/{total} device(s) OK")
    for r in results:
        tag = ("OK" if r["success"] and r["match"] is not False else "FAIL")
        extra = r["error"] or ("MD5 mismatch" if r["match"] is False
                               else "+".join(r["actions"]) or "-")
        log(f"  {tag:4} {r['host']:<18} {extra}")
    return results
