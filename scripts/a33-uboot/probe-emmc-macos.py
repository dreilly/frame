#!/usr/bin/env python3
"""Read-only identity/throughput probe before a long backup.

Usage: sudo python3 -I scripts/a33-uboot/probe-emmc-macos.py diskN <exact-bytes>
Only reads the frame. Writes a private 4 MiB prefix and a JSON report on the Mac.
Uses the upstream backup reader's USB/read-only/whole-disk/name/size guards.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("guarded_emmc", HERE / "emmc-macos.py")
emmc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emmc)
SIZE = 4 * 1024 * 1024
OUT = ROOT / "backups/ms33-emmc-prefix.bin"
REPORT = ROOT / "diagnostics/ms33-emmc-probe.json"


def main():
    if len(sys.argv) != 3 or os.geteuid() != 0:
        sys.exit(__doc__)
    identifier, total = sys.argv[1], int(sys.argv[2])
    if OUT.exists() or REPORT.exists():
        sys.exit("STOP: probe output already exists; refusing to overwrite")
    raw = emmc.open_disk(identifier, total)
    times = []
    reads = []
    fd = os.open(raw, os.O_RDONLY)
    try:
        for _ in range(2):
            start = time.monotonic()
            data = os.pread(fd, SIZE, 0)
            times.append(time.monotonic() - start)
            if len(data) != SIZE:
                sys.exit(f"STOP: short read ({len(data)} bytes)")
            reads.append(data)
    finally:
        os.close(fd)
    if reads[0] != reads[1]:
        sys.exit("STOP: independent prefix reads differ")
    data = reads[0]
    if data[510:512] != b"\x55\xaa":
        sys.exit("STOP: expected an MBR signature")
    if b"\xcc" * 4096 in data:
        sys.exit("STOP: suspicious filler found")
    entries = []
    for i in range(4):
        entry = data[446+i*16:462+i*16]
        if entry[4]:
            entries.append({"index": i+1, "type": entry[4],
                            "start_sector": struct.unpack_from("<I", entry, 8)[0],
                            "sectors": struct.unpack_from("<I", entry, 12)[0]})
    info = {"device": identifier, "total_bytes": total, "prefix_bytes": SIZE,
            "prefix_sha256": hashlib.sha256(data).hexdigest(),
            "read_seconds": times,
            "read_MB_per_second": [SIZE/seconds/1e6 for seconds in times],
            "mbr_partitions": entries}
    os.umask(0o077)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if OUT.read_bytes() != data:
        sys.exit("STOP: saved prefix readback differs")
    with REPORT.open("x") as handle:
        json.dump(info, handle, indent=2)
        handle.write("\n")
    if "SUDO_UID" in os.environ:
        uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
        for path in (OUT, REPORT):
            os.chown(path, uid, gid)
    print(f"Verified two independent 4 MiB reads; saved {OUT.name} on the Mac.")
    print("Read speed: " + ", ".join(f"{rate:.2f} MB/s" for rate in info["read_MB_per_second"]))
    print("MBR partitions:", entries)
    print("No writes to the frame.")


if __name__ == "__main__":
    main()
