#!/usr/bin/env python3
"""
Minimal threaded TFTP server (RFC 1350 + options RFC 2347/2348).

Serves files from a root directory so a network device can pull a firmware
image with `copy tftp: flash:`. Supports read (RRQ) and write (WRQ), the
`blksize`, `tsize` and `timeout` options (needed for large images), and simple
retransmission. Standard-library only.

Security: only the basename of a requested file is used (no path traversal);
files are read from / written to the configured root directory only.

    srv = TftpServer(root=r"C:\\images", bind_ip="0.0.0.0", port=69,
                     log=print)
    srv.start()
    ...
    srv.stop()
"""

from __future__ import annotations

import os
import socket
import struct
import threading
from typing import Callable, Optional

RRQ, WRQ, DATA, ACK, ERROR, OACK = 1, 2, 3, 4, 5, 6
DEFAULT_BLKSIZE = 512
# Cap negotiated block size to stay within a typical 1500-byte MTU
# (1468 data + 4 TFTP + 8 UDP + 20 IP = 1500). Larger blocks get fragmented
# and the fragments are often dropped on routed paths, stalling the transfer.
MAX_BLKSIZE = 1468
MODES = ("netascii", "octet")


class TftpServer:
    def __init__(self, root: str, bind_ip: str = "0.0.0.0", port: int = 69,
                 log: Optional[Callable[[str], None]] = None,
                 allow_write: bool = True, max_blksize: int = MAX_BLKSIZE,
                 progress: Optional[Callable[[str, int, int], None]] = None):
        self.root = os.path.abspath(root)
        self.bind_ip = bind_ip
        self.port = int(port)
        self.log = log or (lambda m: None)
        self.allow_write = allow_write
        self.max_blksize = int(max_blksize)
        # progress(filename, bytes_sent, total_bytes) - called during a read
        self.progress = progress
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        if self._running:
            return
        os.makedirs(self.root, exist_ok=True)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.bind_ip, self.port))
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self.log(f"TFTP server listening on {self.bind_ip}:{self.port} "
                 f"(root: {self.root})")

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self.log("TFTP server stopped")

    @property
    def running(self) -> bool:
        return self._running

    # -- main accept loop --------------------------------------------------
    def _serve(self):
        assert self._sock is not None
        self._sock.settimeout(1.0)
        while self._running:
            try:
                data, client = self._sock.recvfrom(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) < 2:
                continue
            opcode = struct.unpack("!H", data[:2])[0]
            # Transfers run on THIS listening socket (port 69) rather than a
            # new ephemeral port. The device already reaches port 69 (the RRQ
            # arrived), so replies from the same port avoid the Windows
            # ephemeral-port / firewall return-path problem. Transfers are
            # handled inline (serialized), which is fine for firmware pushes.
            try:
                if opcode == RRQ:
                    self._handle_rrq(data[2:], client)
                elif opcode == WRQ:
                    self._handle_wrq(data[2:], client)
                # stray ACK/other packets outside a transfer are ignored
            except OSError as exc:
                self.log(f"  transfer error: {exc}")

    # -- request parsing ---------------------------------------------------
    @staticmethod
    def _parse_request(payload: bytes):
        parts = payload.split(b"\x00")
        filename = parts[0].decode("latin-1", "replace")
        mode = parts[1].decode("latin-1", "replace").lower() if len(parts) > 1 else "octet"
        opts = {}
        rest = parts[2:]
        for i in range(0, len(rest) - 1, 2):
            k = rest[i].decode("latin-1", "replace").lower()
            v = rest[i + 1].decode("latin-1", "replace")
            if k:
                opts[k] = v
        return filename, mode, opts

    def _safe_path(self, filename: str) -> str:
        return os.path.join(self.root, os.path.basename(filename))

    @staticmethod
    def _error(sock, addr, code: int, msg: str):
        pkt = struct.pack("!HH", ERROR, code) + msg.encode() + b"\x00"
        try:
            sock.sendto(pkt, addr)
        except OSError:
            pass

    @staticmethod
    def _oack(opts: dict) -> bytes:
        pkt = struct.pack("!H", OACK)
        for k, v in opts.items():
            pkt += k.encode() + b"\x00" + str(v).encode() + b"\x00"
        return pkt

    # -- read (device pulls a file) ---------------------------------------
    def _handle_rrq(self, payload: bytes, client):
        filename, mode, opts = self._parse_request(payload)
        path = self._safe_path(filename)
        self.log(f"RRQ from {client[0]}:{client[1]} -> {os.path.basename(path)}")
        if not os.path.isfile(path):
            self._error(self._sock, client, 1, "File not found")
            self.log(f"  file not found: {path}")
            return

        filesize = os.path.getsize(path)
        blksize = DEFAULT_BLKSIZE
        negotiated = {}
        if "blksize" in opts:
            try:
                requested = int(opts["blksize"])
                blksize = max(8, min(self.max_blksize, requested))
                negotiated["blksize"] = blksize   # may be smaller than requested
                if blksize < requested:
                    self.log(f"  capping blksize {requested} -> {blksize} "
                             "(avoids UDP fragmentation)")
            except ValueError:
                pass
        if "tsize" in opts:
            negotiated["tsize"] = filesize
        if "timeout" in opts:
            negotiated["timeout"] = opts["timeout"]

        try:
            with open(path, "rb") as fh:
                if negotiated:
                    if not self._send_expect_ack(self._sock, self._oack(negotiated),
                                                 client, 0):
                        self.log("  transfer failed (no OACK ack)")
                        return
                block = 1
                sent = 0
                name = os.path.basename(path)
                while True:
                    chunk = fh.read(blksize)
                    pkt = struct.pack("!HH", DATA, block & 0xFFFF) + chunk
                    if not self._send_expect_ack(self._sock, pkt, client,
                                                 block & 0xFFFF):
                        self.log(f"  transfer failed (no ACK at block {block})")
                        return
                    sent += len(chunk)
                    if self.progress:
                        try:
                            self.progress(name, sent, filesize)
                        except Exception:  # noqa: BLE001
                            pass
                    if len(chunk) < blksize:
                        break
                    block += 1
            self.log(f"  sent {filesize} bytes OK")
        except OSError as exc:
            self.log(f"  read error: {exc}")

    def _send_expect_ack(self, sock, pkt, addr, expect_block, retries=5) -> bool:
        for _ in range(retries):
            try:
                sock.sendto(pkt, addr)
                while True:
                    data, raddr = sock.recvfrom(2048)
                    if raddr[0] != addr[0]:
                        continue
                    if len(data) >= 4 and struct.unpack("!H", data[:2])[0] == ACK:
                        blk = struct.unpack("!H", data[2:4])[0]
                        if blk == expect_block:
                            return True
                    if len(data) >= 2 and struct.unpack("!H", data[:2])[0] == ERROR:
                        return False
                    break  # unexpected -> resend
            except socket.timeout:
                continue
            except OSError:
                return False
        return False

    # -- write (device pushes a file) -------------------------------------
    def _handle_wrq(self, payload: bytes, client):
        filename, mode, opts = self._parse_request(payload)
        path = self._safe_path(filename)
        self.log(f"WRQ from {client[0]}:{client[1]} -> {os.path.basename(path)}")
        if not self.allow_write:
            self._error(self._sock, client, 2, "Writes disabled")
            return
        blksize = DEFAULT_BLKSIZE
        negotiated = {}
        if "blksize" in opts:
            try:
                blksize = max(8, min(self.max_blksize, int(opts["blksize"])))
                negotiated["blksize"] = blksize
            except ValueError:
                pass
        if "timeout" in opts:
            negotiated["timeout"] = opts["timeout"]

        try:
            # acknowledge: OACK if options, else ACK block 0
            first = self._oack(negotiated) if negotiated else struct.pack(
                "!HH", ACK, 0)
            total = 0
            misses = 0
            with open(path, "wb") as fh:
                expected = 1
                self._sock.sendto(first, client)
                while True:
                    try:
                        data, raddr = self._sock.recvfrom(blksize + 4)
                    except socket.timeout:
                        misses += 1
                        if misses >= 5:
                            self.log("  write timeout")
                            return
                        continue
                    if raddr[0] != client[0]:
                        continue
                    if len(data) < 4:
                        continue
                    op, blk = struct.unpack("!HH", data[:4])
                    if op != DATA:
                        continue
                    misses = 0
                    if blk == expected:
                        chunk = data[4:]
                        fh.write(chunk)
                        total += len(chunk)
                        self._sock.sendto(struct.pack("!HH", ACK, blk), client)
                        expected = (expected + 1) & 0xFFFF
                        if len(chunk) < blksize:
                            break
                    else:
                        self._sock.sendto(struct.pack("!HH", ACK, blk), client)
            self.log(f"  received {total} bytes OK")
        except OSError as exc:
            self.log(f"  write error: {exc}")


def local_ips() -> list:
    """Best-effort list of this host's IPv4 addresses for the UI."""
    ips = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips) or ["0.0.0.0"]
