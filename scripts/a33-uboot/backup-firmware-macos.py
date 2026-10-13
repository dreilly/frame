#!/usr/bin/env python3
"""Back up only verified boot/recovery partitions, never write the frame.

Usage: sudo python3 -I scripts/a33-uboot/backup-firmware-macos.py diskN <exact-bytes>

This is a targeted firmware backup, NOT a complete eMMC backup. Each partition is
read independently twice, checked for filler, saved, compressed and verified.
Partition locations are the observed layout of this specific MS33 unit. Every
location/size is rechecked against diskutil before opening the raw disk read-only.
"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "backups/ms33-firmware"
PROBE = ROOT / "diagnostics/ms33-emmc-probe.json"
PREFIX = ROOT / "backups/ms33-emmc-prefix.bin"
CHUNK = 4 * 1024 * 1024
PARTITIONS = [("boot", "s6", 88080384, 16777216),
              ("recovery", "s9", 1195376640, 33554432)]

spec = importlib.util.spec_from_file_location("guarded_emmc", HERE / "emmc-macos.py")
emmc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emmc)


def fail(message):
    sys.exit(f"STOP: {message}")


def partition_info(identifier, suffix, offset, size):
    part = identifier + suffix
    info = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", part]))
    expected = {"DeviceIdentifier": part, "ParentWholeDisk": identifier,
                "PartitionMapPartitionOffset": offset, "TotalSize": size,
                "Content": "Linux", "WritableMedia": False,
                "Internal": False, "BusProtocol": "USB"}
    for key, value in expected.items():
        if info.get(key) != value:
            fail(f"{part}: {key} {info.get(key)!r} != expected {value!r}")


def read_at(fd, length, offset):
    data = os.pread(fd, length, offset)
    if len(data) != length:
        fail(f"short read at {offset}: {len(data)} != {length}")
    return data


def owner_access(paths):
    if "SUDO_UID" in os.environ:
        uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
        for path in paths:
            os.chown(path, uid, gid)


def image_header(data):
    if data[:8] != b"ANDROID!":
        fail("partition does not begin with an Android boot image")
    kernel, ramdisk, second, page = (struct.unpack_from("<I", data, n)[0]
                                     for n in (8, 16, 24, 36))
    if page not in (2048, 4096, 8192, 16384) or not kernel or not ramdisk:
        fail("unexpected Android image geometry")
    aligned = lambda n: (n + page - 1) // page * page
    end = page + aligned(kernel) + aligned(ramdisk) + aligned(second)
    if end > len(data):
        fail("Android image extends beyond its partition")
    return {"kernel_bytes": kernel, "ramdisk_bytes": ramdisk,
            "second_bytes": second, "page_size": page,
            "ramdisk_offset": page + aligned(kernel), "image_aligned_bytes": end}


def capture(fd, name, offset, size):
    target = OUT / f"{name}.img"
    compressed = OUT / f"{name}.img.gz"
    for path in (target, compressed):
        if path.exists():
            fail(f"{path.name} already exists; refusing to overwrite")
    pieces = []
    first = hashlib.sha256()
    started = time.monotonic()
    for pos in range(0, size, CHUNK):
        data = read_at(fd, min(CHUNK, size-pos), offset+pos)
        if b"\xcc" * 4096 in data:
            fail(f"suspicious filler in {name} at partition offset {pos}")
        first.update(data)
        pieces.append(data)
        print(f"{name}: first read {(pos+len(data))*100//size}%", flush=True)
    image = b"".join(pieces)
    header = image_header(image)
    second = hashlib.sha256()
    for pos in range(0, size, CHUNK):
        second.update(read_at(fd, min(CHUNK, size-pos), offset+pos))
        print(f"{name}: independent re-read {(pos+min(CHUNK,size-pos))*100//size}%", flush=True)
    if first.digest() != second.digest():
        fail(f"{name}: independent reads differ")
    with target.open("xb") as handle:
        handle.write(image)
        handle.flush()
        os.fsync(handle.fileno())
    if hashlib.sha256(target.read_bytes()).digest() != first.digest():
        fail(f"{name}: saved image differs")
    with compressed.open("xb") as handle:
        handle.write(gzip.compress(image, compresslevel=6, mtime=0))
        handle.flush()
        os.fsync(handle.fileno())
    if gzip.decompress(compressed.read_bytes()) != image:
        fail(f"{name}: gzip readback differs")
    owner_access([target, compressed])
    result = {"offset_bytes": offset, "partition_bytes": size,
              "sha256": first.hexdigest(), "read_passes": 2,
              "gzip_readback_verified": True, "filler_checked": True,
              "elapsed_seconds": time.monotonic()-started, "android_header": header}
    print(f"Verified {name}: {size} bytes; SHA-256 {result['sha256']}", flush=True)
    return result


def main():
    if len(sys.argv) != 3 or os.geteuid() != 0:
        sys.exit(__doc__)
    identifier, total = sys.argv[1], int(sys.argv[2])
    probe = json.loads(PROBE.read_text())
    if probe["total_bytes"] != total:
        fail("disk size does not match the earlier probe")
    saved = PREFIX.read_bytes()
    if len(saved) != CHUNK or hashlib.sha256(saved).hexdigest() != probe["prefix_sha256"]:
        fail("saved identity prefix is invalid")
    for _, suffix, offset, size in PARTITIONS:
        if offset + size > total:
            fail("partition is outside the disk")
        partition_info(identifier, suffix, offset, size)
    raw = emmc.open_disk(identifier, total)
    if OUT.exists():
        fail("firmware backup directory already exists; refusing to overwrite")
    os.umask(0o077)
    OUT.mkdir(mode=0o700)
    owner_access([OUT])
    manifest = {"complete": False, "scope": "boot and recovery only; NOT full eMMC",
                "total_device_bytes": total, "partitions": {}}
    fd = os.open(raw, os.O_RDONLY)
    try:
        if read_at(fd, CHUNK, 0) != saved:
            fail("live disk identity does not match the previous probe")
        for name, _, offset, size in PARTITIONS:
            manifest["partitions"][name] = capture(fd, name, offset, size)
            path = OUT / "manifest.json"
            path.write_text(json.dumps(manifest, indent=2)+"\n")
            owner_access([path])
    finally:
        os.close(fd)
    manifest["complete"] = True
    path = OUT / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2)+"\n")
    owner_access([path])
    print("Verified targeted firmware backup complete. No writes to the frame.")
    print(f"Files: {OUT}")


if __name__ == "__main__":
    main()
