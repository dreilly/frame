#!/usr/bin/env bash
# Host-only build of the experimental MS33-V2.0 read-only backup helper.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/diagnostics/u-boot"
OUT="$ROOT/diagnostics/ms33-uboot-out"
EXPECTED=e50b1e8715011def8aff1588081a2649a2c6cd47
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$EXPECTED" ]] || { echo 'STOP: unexpected source revision'; exit 1; }
export PATH="$ROOT/diagnostics/build-venv/bin:/opt/homebrew/opt/bison/bin:/opt/homebrew/bin:$PATH"
export SOURCE_DATE_EPOCH=1759104000
# U-Boot 2025.10's host signing tools still require OpenSSL 3's ENGINE API.
export PKG_CONFIG_PATH="/opt/homebrew/opt/openssl@3/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
mkdir -p "$OUT"
ARGS=(O="$OUT" CROSS_COMPILE=arm-none-eabi- HOSTCC=clang HOSTCFLAGS=-I/opt/homebrew/opt/openssl@3/include HOSTLDFLAGS=-L/opt/homebrew/opt/openssl@3/lib)
gmake -C "$SRC" "${ARGS[@]}" ms33_backup_defconfig > "$OUT/configure.log" 2>&1 || { tail -70 "$OUT/configure.log"; exit 1; }
gmake -C "$SRC" "${ARGS[@]}" -j8 > "$OUT/build.log" 2>&1 || { tail -70 "$OUT/build.log"; exit 1; }
python3 - "$OUT" <<'PY'
import hashlib, pathlib, sys
out=pathlib.Path(sys.argv[1]); cfg=(out/'.config').read_text()
required=['CONFIG_MACH_SUN8I_A33=y','CONFIG_SUNXI_NO_PMIC=y','CONFIG_USB_MUSB_GADGET=y','CONFIG_CMD_USB_MASS_STORAGE=y','CONFIG_ENV_IS_NOWHERE=y','# CONFIG_MMC_WRITE is not set','# CONFIG_VIDEO_SUNXI is not set','CONFIG_BOOTCOMMAND="mmc list; ums 0 mmc 1"']
for value in required:
 assert value in cfg, f'Missing required safety/config setting: {value}'
image=(out/'u-boot-sunxi-with-spl.bin').read_bytes()
assert image[4:12]==b'eGON.BT0', 'Not an Allwinner SPL image'
size=int.from_bytes(image[16:20],'little')
assert size <= 0x5e00, f'SPL length {size:#x} too near early stack'
assert (out/'spl/u-boot-spl.bin').stat().st_size<=0x5e00
sha=hashlib.sha256(image).hexdigest()
(out/'u-boot-sunxi-with-spl.sha256').write_text(sha+'  u-boot-sunxi-with-spl.bin\n')
print(f'Built RAM-only read-only helper. SPL image length {size:#x}. SHA-256 {sha}')
PY
