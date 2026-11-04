# NetToolkit

*by Nithin Eluvathingal — MIT Licensed*

A single Windows application that combines three network-engineering tools as
tabs in one window:

1. **Backup** — back up Cisco device configurations over **SSH or Telnet**,
   for a single device or a batch from **Excel**, with optional
   `show tech-support` capture.
2. **Config Builder** — build clean, **copy-paste-ready** switch/router
   configurations from simple inputs (VLANs, ports, EtherChannel, routing,
   HSRP/VRRP, DHCP, ACLs, SNMP, and more). Save/load answers as JSON "specs".
3. **Converter** — translate a switch configuration **between vendors**:
   **Cisco IOS, Arista EOS, Aruba AOS-CX, Huawei VRP, HPE Comware** — any to any.

## Run it

1. Install **Python 3.9+** (tick *Add Python to PATH*; Tkinter is included).
2. Double-click **`Install.bat`** once (installs Netmiko + openpyxl for the
   Backup tab).
3. Double-click **`NetToolkit.bat`** (or run `python toolkit.py`).

The Config Builder and Converter tabs work with no extra packages; only the
Backup tab needs Netmiko/openpyxl.

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
| `backup_panel.py` / `config_panel.py` / `convert_panel.py` | Tab UIs |

## License
Released under the **MIT License** — © 2026 Nithin Eluvathingal.
See the [LICENSE](LICENSE) file for the full text. The author and license are
also shown in the app's title bar, status bar, and **Help → About** dialog.
