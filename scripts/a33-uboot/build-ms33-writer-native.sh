#!/usr/bin/env bash
# HOST-ONLY build. Does not connect to or write the frame.
# MMC writes are allowlisted in mmc_write.c to this unit's two boot ranges.
# Host UMS remains read-only, erase/fastboot/environment writes disabled.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/diagnostics/u-boot"
OUT="$ROOT/diagnostics/ms33-writer-out"
EXPECTED=e50b1e8715011def8aff1588081a2649a2c6cd47
[[ "$(git -C "$SRC" rev-parse HEAD)" == "$EXPECTED" ]] || { echo 'STOP: unexpected source revision'; exit 1; }
export PATH="$ROOT/diagnostics/build-venv/bin:/opt/homebrew/opt/bison/bin:/opt/homebrew/bin:$PATH"
export SOURCE_DATE_EPOCH=1759104000
export PKG_CONFIG_PATH="/opt/homebrew/opt/openssl@3/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
mkdir -p "$OUT"
ARGS=(O="$OUT" CROSS_COMPILE=arm-none-eabi- HOSTCC=clang HOSTCFLAGS=-I/opt/homebrew/opt/openssl@3/include HOSTLDFLAGS=-L/opt/homebrew/opt/openssl@3/lib)
gmake -C "$SRC" "${ARGS[@]}" ms33_backup_defconfig > "$OUT/configure.log" 2>&1
"$SRC/scripts/config" --file "$OUT/.config" --enable MMC_WRITE --disable SPL_MMC_WRITE --disable MMC_HW_PARTITIONING --disable SUPPORT_EMMC_BOOT --disable SUPPORT_EMMC_RPMB --set-str BOOTCOMMAND 'source 0x47000000; ums 0 mmc 1'
gmake -C "$SRC" "${ARGS[@]}" olddefconfig >> "$OUT/configure.log" 2>&1
gmake -C "$SRC" "${ARGS[@]}" -j8 > "$OUT/build.log" 2>&1 || { tail -70 "$OUT/build.log"; exit 1; }
python3 - "$SRC" "$OUT" <<'PY'
import hashlib,pathlib,re,subprocess,sys
if not __debug__: raise SystemExit('STOP: optimized Python disables build safety checks')
src,out=map(pathlib.Path,sys.argv[1:]);cfg=(out/'.config').read_text()
required=['CONFIG_MACH_SUN8I_A33=y','CONFIG_SUNXI_NO_PMIC=y','CONFIG_USB_MUSB_GADGET=y','CONFIG_CMD_USB_MASS_STORAGE=y','CONFIG_ENV_IS_NOWHERE=y','CONFIG_MMC_WRITE=y','# CONFIG_SPL_MMC_WRITE is not set','# CONFIG_MMC_HW_PARTITIONING is not set','# CONFIG_SUPPORT_EMMC_BOOT is not set','# CONFIG_SUPPORT_EMMC_RPMB is not set','# CONFIG_VIDEO_SUNXI is not set','# CONFIG_USB_FUNCTION_FASTBOOT is not set','CONFIG_CMD_SOURCE=y','CONFIG_CMD_MEMORY=y','CONFIG_CMD_CRC32=y','CONFIG_CRC32_VERIFY=y','CONFIG_BOOTCOMMAND="source 0x47000000; ums 0 mmc 1"','CONFIG_PREBOOT=""']
for setting in required:
 assert setting in cfg, f'Missing required setting: {setting}'
for setting in ['CONFIG_FASTBOOT=y','CONFIG_FASTBOOT_FLASH=y','CONFIG_CMD_SAVEENV=y','CONFIG_ENV_IS_IN_MMC=y','CONFIG_ENV_IS_IN_FAT=y','CONFIG_UDP_FUNCTION_FASTBOOT=y','CONFIG_TCP_FUNCTION_FASTBOOT=y']:
 assert setting not in cfg, f'Forbidden setting: {setting}'
assert 'initially_ro = 1;' in (src/'drivers/usb/gadget/f_mass_storage.c').read_text()
source=(src/'drivers/mmc/mmc_write.c').read_text()
for guard in ['block_dev->lba != 61071360ULL','start == 191892 && blkcnt == 9264','start == 172032 && blkcnt == 2','0x419b2800','0x439b2800','0x41000000','0x43000000','never erase any storage']:
 assert guard in source, f'Missing driver guard: {guard}'
disasm=subprocess.check_output(['arm-none-eabi-objdump','-d',str(out/'u-boot')],text=True)
for name,value in [('ums_write_sector',0),('mmc_berase',0),('do_mmc_boot_wp',1)]:
 function=disasm.split(f'<{name}>:\n',1)[1].split('\n\n',1)[0]
 instructions=[line for line in function.splitlines() if re.match(r'^[0-9a-f]+:\s',line)]
 assert len(instructions)==2 and f'movs\tr0, #{value}' in instructions[0] and 'bx\tlr' in instructions[1], f'{name} is not the expected refusal stub: {function}'
image=(out/'u-boot-sunxi-with-spl.bin').read_bytes()
assert image[4:12]==b'eGON.BT0'
size=int.from_bytes(image[16:20],'little')
assert size<=0x5e00 and (out/'spl/u-boot-spl.bin').stat().st_size<=0x5e00
assert 'CONFIG_TEXT_BASE=0x4a000000' in cfg
sha=hashlib.sha256(image).hexdigest()
(out/'u-boot-sunxi-with-spl.sha256').write_text(sha+'  u-boot-sunxi-with-spl.bin\n')
(out/'source.patch').write_bytes(subprocess.check_output(['git','-C',str(src),'diff']))
(out/'mmc-bwrite.disasm').write_text(disasm.split('<mmc_bwrite>:\n',1)[1].split('\n\n',1)[0]+'\n')
print(f'Built host-only guarded writer; UMS/erase stubs verified. SPL length {size:#x}. SHA-256 {sha}')
PY
