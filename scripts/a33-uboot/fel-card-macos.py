#!/usr/bin/env python3
"""macOS port of the FEL SD card steps in docs/allwinner-a33-pf1007l.md, section 2.

Usage (run from the repo root, with sudo):
  sudo python3 -I scripts/a33-uboot/fel-card-macos.py backup  diskN <exact-bytes>
  sudo python3 -I scripts/a33-uboot/fel-card-macos.py write   diskN <exact-bytes>
  sudo python3 -I scripts/a33-uboot/fel-card-macos.py restore diskN <exact-bytes>

The size argument is the card's exact byte count from `diskutil info`. It guards
against a disk number that changed after an unplug/replug.
"""

import gzip
import hashlib
import os
import plistlib
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STUB_PATH = REPO / "diagnostics/sunxi-tools/bin/fel-sdboot.sunxi"
STUB_SHA256 = "2ccec08a026840571f3804671ba72afae840db27112a43f2b1f122075bc808bc"
BACKUP_PATH = REPO / "backups/a33-fel-card-prefix.bin.gz"
PREFIX_SIZE = 4 * 1024 * 1024
STUB_OFFSET = 8192
STUB_SIZE = 8192


def fail(message):
    sys.exit(f"STOP: {message}")


def disk_info(identifier):
    output = subprocess.check_output(["diskutil", "info", "-plist", identifier])
    return plistlib.loads(output)


def check_card(identifier, expected_size):
    if not identifier.startswith("disk") or "s" in identifier[4:]:
        fail("pass a whole disk like disk4, not a partition")

    info = disk_info(identifier)
    if info.get("Internal", True):
        fail("disk is not external")
    if not info.get("RemovableMedia") and not info.get("Removable"):
        fail("disk is not removable media")
    if info.get("BusProtocol") != "USB":
        fail(f"unexpected protocol {info.get('BusProtocol')}")
    if info.get("TotalSize") != expected_size:
        fail(f"size {info.get('TotalSize')} != expected {expected_size}")
    if not info.get("WholeDisk"):
        fail("not a whole disk")

    subprocess.check_call(["diskutil", "unmountDisk", identifier])
    for line in subprocess.check_output(["mount"], text=True).splitlines():
        if line.startswith(f"/dev/{identifier}s") or line.startswith(f"/dev/{identifier} "):
            fail(f"still mounted: {line}")

    return f"/dev/r{identifier}"


def read_prefix(raw_path):
    fd = os.open(raw_path, os.O_RDONLY)
    try:
        first = os.pread(fd, PREFIX_SIZE, 0)
        second = os.pread(fd, PREFIX_SIZE, 0)
    finally:
        os.close(fd)
    if len(first) != PREFIX_SIZE:
        fail(f"short read: {len(first)} bytes")
    if first != second:
        fail("independent re-read differs")
    return first


def check_layout(prefix):
    if prefix[510:512] != b"\x55\xaa":
        fail("expected an MBR signature")
    entries = [prefix[446 + i * 16 : 462 + i * 16] for i in range(4)]
    active = [entry for entry in entries if entry[4]]
    if not active or any(entry[4] == 0xEE for entry in active):
        fail("GPT or empty layout not supported")
    for entry in active:
        start = struct.unpack_from("<I", entry, 8)[0]
        if start < 8192:
            fail(f"partition starts at sector {start}, too close to the stub")
        print(f"  partition type {entry[4]:#04x} starts at sector {start}")


def load_stub():
    stub = STUB_PATH.read_bytes()
    if len(stub) != STUB_SIZE or stub[4:12] != b"eGON.BT0":
        fail("stub has the wrong size or magic")
    if hashlib.sha256(stub).hexdigest() != STUB_SHA256:
        fail("stub SHA-256 mismatch")
    return stub


def backup(raw_path):
    prefix = read_prefix(raw_path)
    check_layout(prefix)
    BACKUP_PATH.parent.mkdir(exist_ok=True)
    os.umask(0o077)
    with gzip.open(BACKUP_PATH, "xb") as handle:
        handle.write(prefix)
    if gzip.decompress(BACKUP_PATH.read_bytes()) != prefix:
        fail("backup readback mismatch")
    print("Card prefix backed up:", BACKUP_PATH)
    print("SHA-256:", hashlib.sha256(prefix).hexdigest())


def load_backup():
    before = gzip.decompress(BACKUP_PATH.read_bytes())
    if len(before) != PREFIX_SIZE:
        fail("backup has the wrong length")
    return before


def write_region(raw_path, data, expected_prefix):
    fd = os.open(raw_path, os.O_RDWR)
    try:
        written = os.pwrite(fd, data, STUB_OFFSET)
        os.fsync(fd)
    finally:
        os.close(fd)
    if written != len(data):
        fail(f"short write: {written} bytes")
    if read_prefix(raw_path) != expected_prefix:
        fail("card readback mismatch")


def write(raw_path):
    stub = load_stub()
    before = load_backup()
    if read_prefix(raw_path) != before:
        fail("card no longer matches the backup; was it swapped?")
    check_layout(before)
    expected = before[:STUB_OFFSET] + stub + before[STUB_OFFSET + STUB_SIZE :]
    write_region(raw_path, stub, expected)
    print("Exactly 8192 bytes changed at byte offset 8192. Readback verified.")


def restore(raw_path):
    stub = load_stub()
    before = load_backup()
    current = read_prefix(raw_path)
    expected_written = before[:STUB_OFFSET] + stub + before[STUB_OFFSET + STUB_SIZE :]
    if current not in (before, expected_written):
        fail("card matches neither the backup nor the stubbed state")
    write_region(raw_path, before[STUB_OFFSET : STUB_OFFSET + STUB_SIZE], before)
    print("Original bytes restored. Readback verified.")


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("backup", "write", "restore"):
        sys.exit(__doc__)
    if os.geteuid() != 0:
        fail("run with sudo")
    action, identifier, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
    raw_path = check_card(identifier, size)
    {"backup": backup, "write": write, "restore": restore}[action](raw_path)


if __name__ == "__main__":
    main()
