# Changelog

All notable changes to **NetToolkit**. Versioning follows
[Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-11-22

### Added
- **FortiGate tab** — FortiOS 7.x configuration builder spanning Day 0 → Day 100:
  - Day 0: hostname, timezone, admin accounts + hardening, password policy,
    DNS, NTP, interfaces, static routes, DHCP servers.
  - Day 1: address objects/groups, IP pools, VIPs (port-forward), firewall
    policies with NAT and AV / Web filter / IPS / App control + SSL inspection.
  - Day 2+: syslog, FortiAnalyzer, SNMP, HA, FortiGuard auto-updates.
  - `forti_builder.py` engine (with CLI) and `forti_panel.py` UI.
- **Upgrade tab** — Cisco IOS/IOS-XE firmware push and verification:
  - Built-in **TFTP server** (`tftp_server.py`): RRQ/WRQ, `blksize`/`tsize`/
    `timeout` option negotiation, retransmission, path-traversal safe.
  - `upgrade.py`: drives the IOS `copy tftp:` dialog, `verify /md5`, sets the
    boot variable + saves, and reloads over SSH/Telnet.
  - Local-file **MD5** compared against the device `verify /md5` result, with a
    clear MATCH / MISMATCH outcome.
  - **Batch upgrade from an Excel inventory** (many devices at once): per-device
    MD5 gating (set-boot/reload only on a match), a `reload=yes` + "Allow
    reload" safety toggle, inventory template generator, and a pass/fail summary.
  - **SCP transfer** option (reliable, over the SSH session, built-in MD5) as the
    default alternative to TFTP, plus a **Stop** button to cancel a running or
    stuck operation.
  - **Upload progress** - a live percentage and progress bar during the transfer
    (both SCP and TFTP, single device and batch).

### Changed
- README updated with the two new tabs and an Upgrade how-to.
- Upgrade tab log is now scrollable and written to `logs\upgrade_*.log`, with
  Clear / Save log / Open logs folder buttons.
- FortiGate and Upgrade tabs are now vertically scrollable, so the log console
  is no longer squeezed to zero height on smaller windows.

### Fixed
- SCP upload killing the SSH session: SCP now runs on its own dedicated SSH
  connection, so the device closing the SCP channel at end-of-transfer no longer
  breaks the main session (verify / set-boot / reload keep working). The normal
  IOS end-of-transfer channel close is treated as success.
- TFTP transfers failing with "no ACK": the server now runs the whole transfer
  from the listening port (e.g. 69) instead of a new ephemeral port, so a device
  that can reach port 69 can also reach the data stream (fixes Windows
  ephemeral-port / firewall return-path failures).
- TFTP transfers of large images stalling: the negotiated block size is capped
  to an MTU-safe 1468 bytes, so DATA packets are not fragmented (and dropped) on
  routed paths.

## [1.0.0] - 2026-11-04

### Added
- Initial release with three tabs:
  - **Backup** — Cisco config backup over SSH/Telnet (single device or Excel
    batch), optional `show tech-support`.
  - **Config Builder** — copy-paste-ready Cisco switch/router configs.
  - **Converter** — multi-vendor switch config translation across Cisco, Arista,
    Aruba (AOS-CX), Huawei (VRP) and HPE Comware.
- Application icon, About dialog, menu bar.
- MIT License; author and license surfaced in the title bar, header and status
  bar.
