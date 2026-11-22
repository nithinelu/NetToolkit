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

### Changed
- README updated with the two new tabs and an Upgrade how-to.
- Upgrade tab log is now scrollable and written to `logs\upgrade_*.log`, with
  Clear / Save log / Open logs folder buttons.

### Fixed
- TFTP transfers of large images stalling with "no ACK": the server now caps
  the negotiated block size to an MTU-safe 1468 bytes, so DATA packets are not
  fragmented (and dropped) on routed paths.

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
