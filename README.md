# NetToolkit

**v1.1.0** · *by Nithin Eluvathingal* · MIT Licensed

A single Windows application that combines network-engineering tools as tabs in
one window:

1. **Backup** — back up Cisco device configurations over **SSH or Telnet**,
   for a single device or a batch from **Excel**, with optional
   `show tech-support` capture.
2. **Config Builder** — build clean, **copy-paste-ready** switch/router
   configurations from simple inputs (VLANs, ports, EtherChannel, routing,
   HSRP/VRRP, DHCP, ACLs, SNMP, and more). Save/load answers as JSON "specs".
3. **Converter** — translate a switch configuration **between vendors**:
   **Cisco IOS, Arista EOS, Aruba AOS-CX, Huawei VRP, HPE Comware** — any to any.
4. **FortiGate** — build **FortiOS firewall** configurations from **Day 0 to
   Day 100**: system bring-up (hostname, admins + hardening, DNS/NTP,
   interfaces, routing, DHCP), deployment (address objects, IP pools, VIPs,
   firewall policies with NAT + AV/Web/IPS/App + SSL inspection), and
   operations (syslog, FortiAnalyzer, SNMP, HA, auto-updates).
5. **Upgrade** — push a firmware image to a Cisco IOS/IOS-XE device with a
   **built-in TFTP server**, run the upgrade commands, and verify integrity by
   **MD5** (local file vs. `verify /md5` on the device).

## What's new in 1.1.0
- **FortiGate** tab — FortiOS Day 0 → Day 100 configuration builder.
- **Upgrade** tab — built-in TFTP server, IOS image push, and MD5 verification.
- App **icon**, **About** dialog, menu bar, and author/MIT-license shown in the
  title bar, header, and status bar.

See [CHANGELOG.md](CHANGELOG.md) for the full history.

## Run it

1. Install **Python 3.9+** (tick *Add Python to PATH*; Tkinter is included).
2. Double-click **`Install.bat`** once (installs Netmiko + openpyxl for the
   Backup tab).
3. Double-click **`NetToolkit.bat`** (or run `python toolkit.py`).

The Config Builder and Converter tabs work with no extra packages; only the
Backup tab needs Netmiko/openpyxl.

**Transfer method** — choose **SCP** (default; reliable over the SSH session,
no TFTP server or extra firewall ports, verifies MD5 automatically) or **TFTP**
(the built-in server). A **Stop** button cancels a running or stuck operation.

## Tab 1 — Backup
- *Single device* or *From Excel* (host/username/password required; optional
  protocol, family, enable secret, port, name). A **Create template** button
  writes the `.xlsx`.
- Checkbox to also capture `show tech-support` with a configurable timeout.
- Saved to `backups\`; a per-run log goes to `logs\`.

## Tab 2 — Config Builder
- Tabs for System/Users/SSH, VLANs & switchports, IP & interfaces, routing,
  and services/security.
- **Generate**, then **Copy** or **Save**; **Load/Save spec** (JSON) to reuse.

## Tab 3 — Converter
- Pick **From** and **To** vendors, paste or load a config, click **Convert**.
- Handles the common constructs: hostname, VLANs + names, interface
  descriptions, access/trunk switchports (access VLAN, native/PVID, allowed
  VLANs), L3 IP addresses, and admin state.
- Anything it doesn't recognise is preserved at the end as commented
  **"unconverted"** lines — nothing is silently dropped.
- **Interface names are kept as-is** (naming differs per platform, e.g.
  `Gi1/0/1` vs `1/1/1` vs `GigabitEthernet0/0/1`) — review them before applying.

### Command-line equivalents
```bat
python cisco_backup.py --excel devices.xlsx --show-tech
python config_builder.py --example spec.json
python config_builder.py --load spec.json -o sw1.txt
python vendor_convert.py --from cisco --to huawei input.txt -o out.txt
```

## Caution
Generated and converted configuration is a **starting point, not gospel** —
always review before pasting into production. The converter covers common L2/L3
switching constructs, not full feature parity (no routing protocols, QoS,
security policies, etc.). Keep credentials and backup files somewhere safe.

## Files
| File | Role |
|------|------|
| `toolkit.py` | Main window (the three tabs, menu, About) |
| `about.py` | App name / version / author / license metadata |
| `theme.py` | Shared visual theme |
| `cisco_backup.py` | Backup engine + CLI |
| `config_builder.py` | Config generation engine + CLI/wizard |
| `vendor_convert.py` | Multi-vendor converter engine + CLI |
| `forti_builder.py` | FortiGate (FortiOS) config engine + CLI |
| `tftp_server.py` | Built-in TFTP server (RRQ/WRQ, blksize/tsize) |
| `upgrade.py` | IOS upgrade helpers (copy, verify /md5, boot, reload) |
| `*_panel.py` (backup/config/convert/forti/upgrade) | Tab UIs |

### Upgrade tab — how it works
1. **Start the TFTP server** on a reachable interface (default port 69 — needs
   the Windows firewall to allow it; use a higher port if 69 is blocked/in use).
2. **Pick the image**; its local **MD5** is computed (compare to the vendor's).
3. **Connect** to the device, then **Upload via TFTP** (drives the IOS
   `copy tftp:` dialog), **Verify MD5 on device** (`verify /md5` vs. the local
   hash), **Set boot & save**, and optionally **Reload** (with confirmation).

**Batch from Excel** — upgrade many devices at once from an inventory
(`host, protocol, username, password, secret, image, dest_fs, dest_name,
expected_md5, set_boot, reload`). Use **Create template** to get the sheet.
Choose which steps to run (Upload / Verify MD5 / Set boot & save / Allow
reload); **set-boot and reload only run on a device whose MD5 matches**, and
reload additionally requires both the row's `reload=yes` and the **Allow
reload** safety toggle. A pass/fail summary is printed at the end.

Upload/verify/boot/reload act on a **real device** — review and test on one unit
first. Reload reboots the device and drops the session.

### FortiGate notes
The FortiGate tab generates **FortiOS 7.x CLI** grouped as Day 0 / Day 1 /
Day 2+. It applies the built-in `default` AV/Web/IPS/App profiles and
`certificate-inspection`/`deep-inspection` SSL profiles; a few fields vary by
model/version, so review before pasting. Based on Fortinet's admin/CLI and
hardening guides.

## License
Released under the **MIT License** — © 2026 Nithin Eluvathingal.
See the [LICENSE](LICENSE) file for the full text. The author and license are
also shown in the app's title bar, status bar, and **Help → About** dialog.
