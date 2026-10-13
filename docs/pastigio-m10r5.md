# Pastigio M10R5 / MS33-V2.0

> **Reading note:** this is a chronological engineering record, so early sections preserve states that were later superseded. The authoritative current state is in the final sections, **Live USB diagnosis and permanent role correction**, **Launcher, browser and dashboard kiosk**, and the root `README.md`.

## Goal

Repurpose the frame into a regular Android interface plus a compatible Chromium/WebView full-screen, auto-starting web dashboard, like Wes Bos's photo-frame project. Presence-based dimming is a later stretch goal, not a prerequisite. Keep verified private backups of firmware portions changed and an undo path before persistent writes.

### Scope revision agreed with the owner

The owner explicitly does not need existing photos/user data preserved. The 1-bit/12 MHz recovery reader measured 1.41 MB/s; independently reading all 31.3 GB twice would take about 12 hours. Do NOT insist on a full eMMC backup. Instead, independently verify the complete boot and recovery partitions before a boot change, and back up specific system files/APKs before changing those later. This is NOT a full-device recovery image. Aim for Android access first; do not replace the Android OS. Boot firmware now identifies Android 6.0.1; confirm runtime API/ABI over ADB before selecting the latest compatible browser/WebView. APKMirror metadata confirms a standalone ARM-v7a WebView 106.0.5249.126 variant supports Android 6.0/API 23; this confirms compatibility, not yet the final selected version or installed-provider eligibility.

## Confirmed observations

- Label and Frameo About: Pastigio M10R5 / DPF M10R5; 1280x800; external 5V/2A DC adapter.
- Frameo app v1.28.14 (58400). This is not the Android OS/build version.
- PCB MS33-V2.0, Allwinner marking R6377BA; XR819s Wi-Fi. FEL identity query confirms A33 (`soc=00001667`).
- Frameo beta and ADB toggles were enabled. Normal USB never enumerated, with photo-transfer enabled or disabled. Network ADB port 5555 refused connections.
- An iPhone enumerated on the tested USB connection. The frame itself did not enumerate until FEL.
- The red Recovery screen is Frameo app-level recovery, NOT Android recovery.
- Holding the exterior reboot pinhole during power-on did not yield FEL in the observed test. The PCB has an empty UPDATE switch footprint near the USB/power edge, matching the reference MS33 board layout; it was not shorted.
- A special SD card successfully entered stable, queryable FEL. USB and `sunxi-fel version` both work. The approved boot-only ADB patch is now persistently applied and independently verified twice; other firmware partitions remain untouched.

## Card preparation

- Positively identified USB removable 3,904,897,024-byte card, FAT32 MBR partition starting at sector 8192.
- Saved the first 4 MiB to `backups/a33-fel-card-prefix.bin.gz` (private).
- Wrote exactly 8192 bytes at offset 8192, independently verified the complete prefix against the original plus the stub.
- Official stub: linux-sunxi/sunxi-tools commit `d7bbd172a5da601a08f94479de308c6fb714a19a`, `bin/fel-sdboot.sunxi`, SHA-256 `2ccec08a026840571f3804671ba72afae840db27112a43f2b1f122075bc808bc`.
- Guarded card script from wesbos/photo-frame-dashboard commit `fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03`: `scripts/a33-uboot/fel-card-macos.py`.
- AppleScript privileged helper was denied raw disk access. The owner successfully ran guarded backup/write/eject commands from their terminal.
- Undo: remove both USB and DC, remove the SD card, reconnect normal power. Restore the card using the guarded script if desired, re-identifying disk number and exact size first.

## Host tools / current state

- macOS Apple silicon. `diagnostics/sunxi-tools-src/sunxi-fel` built locally at the pinned upstream revision above.
- Current runtime state: normal Android boot with stable USB ADB after a RAM-only role correction. TCP 5555 is closed in RAM; `sys.boot_completed=0`, `service.adb.tcp.port=0`, OTG role `2`, gadget `CONFIGURED`. Do not reboot before applying or deliberately restoring the prepared permanent role transition, because the currently flashed temporary image would reopen TCP 5555.
- No Docker or ARM cross-compiler was initially installed. Native GNU ARM cross-compiler and GNU make now installed; the MS33 read-only build succeeded.
- U-Boot v2025.10 at `e50b1e8715011def8aff1588081a2649a2c6cd47`, built with native host Clang, arm-none-eabi GCC 16.2.0, GNU make, OpenSSL 3, and isolated Python build environment. Python-3/SWIG and Darwin extension-linking compatibility fixes affect host tools only.
- RAM payload: `diagnostics/ms33-uboot-out/u-boot-sunxi-with-spl.bin`; SHA-256 `1a67b39150f93ed867d67adb037f34421c5941711dc51c84deeb4bc4467919a2`. SPL eGON length 0x4000, below the early-stack limit. Source diff and custom DTS/config saved alongside it.
- Payload loaded successfully into RAM after the owner agreed to begin the previously proposed RAM-only backup route. No flash write performed.
- U-Boot exposes internal eMMC as UMS disk 0; macOS confirms Media Read-Only Yes. Positively identified external USB disk of 31,268,536,320 bytes (61,071,360 sectors), with FAT32 userdata and multiple Linux partitions. Disk number can change after replug; recheck every time.
- Three write protections: UMS callback returns zero (verified ARM disassembly), LUN initially_ro, and `MMC_WRITE`/`SPL_MMC_WRITE` disabled. Fastboot flash disabled; environment nowhere, preboot empty, video off. MMC2 mapped as U-Boot device 1. No PMIC; CPU 408 MHz; conservative eMMC bus 1-bit / 12 MHz, which may be slow. START STOP UNIT patched to exit only on actual unload, not idle-stop.
- Raw eMMC reads ran successfully from the owner's approved Terminal. Boot/recovery backups are complete. Next privilege boundary: obtain explicit approval before a persistent boot patch; current RAM helper deliberately cannot write.
- Homebrew dependencies: libusb, dtc, pkgconf. Automatic brew cleanup unexpectedly removed unrelated packages; those were reinstalled (some newer). Active NVM Node v24.1.0 was unaffected. Further brew commands explicitly disable automatic update/cleanup/autoremove.

## Historical phase checklist

1. DONE: build and inspect MS33-specific, RAM-only U-Boot with USB storage writes refused and LUN read-only.
2. DONE: load the RAM payload (no frame-flash write), identify eMMC size and preliminary partition layout.
3. DONE: verified two independent 4 MiB probe reads at 1.41 MB/s, then complete targeted boot/recovery backup with `scripts/a33-uboot/backup-firmware-macos.py`. Both partitions passed independent reads, exact size, SHA-256, gzip readback and suspicious-filler checks.
   - This unit's observed boot partition: 16,777,216 bytes at offset 88,080,384 (sector 172032).
   - Observed recovery partition: 33,554,432 bytes at offset 1,195,376,640 (sector 2334720).
   - The script rechecks whole-disk identity/read-only status, live prefix against the saved probe, and each partition's exact diskutil offset/size before reading. Its guard tests passed.
   - No frame writes yet. The historical FAT32 userdata MBR entry extends slightly beyond reported physical capacity; do not assume its advertised boundary is writable.
   - Android platform-tools 37.0.1 installed; `adb` is available for the next stage.
4. Offline inspection, ADB patch preparation, and owner approval DONE (details below). Guarded RAM-only writer is built/tested; after the initial receive timeout, the bounded-read retry verified all four RAM payloads and executed the approved apply script. Read-only UMS returned as disk4 with the expected geometry. COMPLETE: user-Terminal full boot readback matches the approved patch byte-for-byte twice; Android image ID valid; plan applied=true. Normal Android/Frameo boot confirmed by the owner after removing FEL card. PENDING: resolve normal-boot USB/ADB; Mac sees no Android USB device and ADB TCP port at previous IP is refused. Try patched photo-transfer mode/USB hotplug before proposing another firmware change. Do not assume PF1007L partitions/boot hashes or the other Pastigio's FAT32 userdata layout.
5. DONE: confirmed Android 6.0.1/API 23/ARMv7, retained compatible system WebView 106, and installed a HOME-capable kiosk plus browser/launcher.
6. PARTIAL: reboot/autostart, networking, display, navigation, and security behavior are verified. Owner-specific dashboard URL, data, design, integrations, and hosting remain for the web-app phase in `apps/ms33-dashboard/`.

## Verified firmware and ADB patch (APPLIED AND VERIFIED)

- Private originals: `backups/ms33-firmware/`, manifest marked complete.
- Original boot SHA-256: `437f65ffb4b80ea6db3a4642bbc91a38210e21bee4a2a9c202856b72132ea560`.
- Original recovery SHA-256: `98eace612f4ff5793d91a29a52989bb591bcd628095aa349d96b1d08db154e6b`.
- Both Android legacy header IDs match the kernel/ramdisk contents. Both kernels are 10,165,848 bytes; boot ramdisk offset 10,168,320; allocated slot 4,743,168. Offline analysis at `diagnostics/ms33-ramdisk/`.
- Boot fingerprint: `Allwinner/astar_xr819/astar-xr819:6.0.1/MOB30R/20251117:eng/test-keys`. Despite the `eng` fingerprint, shipped defaults are `ro.secure=1`, `ro.debuggable=0`, `persist.sys.usb.config=none`. ADB service exists but is disabled until triggered; its binary lacks the `ro.secure` property string, so do not assume changing that property enables root.
- Host ADB generated a standard keypair in `~/.android/`. Only the `.pub` file was read by the patch builder; private key was not copied, inspected, or embedded.
- `scripts/a33-uboot/make-ms33-adb-patch.py` prepares a unit-hash-locked, offline-only patch. It changes only `init.sun8i.usb.rc` and adds `adb_keys` with the Mac's public key. It selects USB ADB at boot completion and adds ADB alongside existing photo-transfer mode. Both new actions set the transient `service.adb.tcp.port=-1`; the boot action stops/restarts adbd so an existing network listener is not retained. Kernel, recovery, default properties, adbd binary, and SELinux policy are unchanged. Root and network ADB are NOT enabled.
- Prepared private outputs: `diagnostics/ms33-adb-patch/`. Patched full-boot SHA-256: `0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33`. The earlier offline candidate without explicit TCP disabling is retained at `diagnostics/ms33-adb-patch-v1/` and must NOT be used.
- Exact intended write ranges, ramdisk first then header: sectors `[191892,201156)` (4,743,168 bytes), and `[172032,172034)` (1024 bytes). No writes elsewhere. Original range payloads are included for undo; the full original boot partition is also available.
- `scripts/a33-uboot/test-ms33-adb-patch.py`: nine tests passed. Includes independent upstream Android/newc parser, macOS `cpio -it` validation, exact in-memory apply/undo roundtrip against original partitions, corrupt/truncated archive/image rejection, stock-action guard, duplicate-file rejection, and public-key validation. Output-overwrite guard tested separately.
- Current UMS disk remains read-only. Preparing files does NOT apply anything. Before applying: validate all RAM payloads, current eMMC originals and each read command; guarded writer must reread/check ramdisk before writing the header and support restoring originals even after a partial failure. No write-capable helper has been loaded.
- After applying, attempt USB `adb devices`; Frameo may still override USB settings later. Do not claim success until normal-boot enumeration and authorization are observed. Keep root and WebView-provider replacement separate from this initial access patch.

## Approved writer preparation and execution

- Owner explicitly approved the proposed boot-only ADB change after clarification that Frameo stays installed. This approval does not cover removing Frameo, replacing Android, or installing a different bootloader.
- New RAM-only helper: `diagnostics/ms33-writer-out/u-boot-sunxi-with-spl.bin`; SHA-256 `9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a`. SPL length 0x4000. Original read-only helper remains intact in `diagnostics/ms33-uboot-out/`.
- Host builder: `scripts/a33-uboot/build-ms33-writer-native.sh`. Same pinned source/board config, MMC writes enabled only in main U-Boot; SPL writes disabled. Hardware partitioning, eMMC boot-management/RPMB, fastboot and persistent environment writes disabled. `mmc wp` is a constant-failure stub. Disassembly verifies UMS write/erase refusal stubs and the write-protection stub.
- `drivers/mmc/mmc_write.c` adds a lower-level allowlist: U-Boot device 1, hwpart 0, 512-byte blocks, exactly 61,071,360 sectors. Only whole approved ramdisk/header write ranges are accepted, and only from their known original/patched RAM pointers. This is NOT a generic write-capable storage exporter; UMS still refuses every host write.
- `scripts/a33-uboot/prepare-ms33-writer.py` prepares private apply/check/restore scripts at `diagnostics/ms33-adb-patch/writer/`, bound to full original/patched boot CRCs plus verified prefix CRC. Before apply, live boot must match all 16 MiB of the original. Every read/write/compare is chained. Ramdisk is written/read/compared before header; full image is reread/compared afterward. Any apply failure attempts original restoration. Explicit restore supports partial writes, provided bytes outside approved ranges still match originals.
- Original boot RAM: 0x41000000..0x42000000; patched: 0x43000000..0x44000000; read buffer: 0x45000000..0x46000000; prefix: 0x46000000..0x46400000; script: 0x47000000; main U-Boot entry: 0x4a000000. No overlap/wrap. Old writer candidate retained at `writer-v1/` must NOT be used.
- `scripts/a33-uboot/load-ms33-writer.py`: without `--execute`, validates host files only. With explicit apply/restore execution, selects this frame's SID `0461872a:a0088204:acf77697:00000000`, loads SPL/main without executing main, uploads payloads, independently reads back all RAM payloads and verifies SHA-256, then executes main U-Boot. Script and helper hash pins are checked; script is reconstructed against the reviewed generator. Use this loader, not direct `sunxi-fel uboot` on the writer image.
- `scripts/a33-uboot/verify-ms33-boot-macos.py`: guarded user-Terminal verifier; validates read-only USB whole disk/partition identity, matches live prefix, reads complete boot twice, compares with the original/approved patched image and checks Android image ID. Only then marks the patch applied. No frame writes.
- Independent headless source/disassembly review found no blocker in exact apply/restore flow, but highlighted eMMC management commands and optimized Python checks. Management commands were disabled/stubbed; preparation/build scripts explicitly reject optimized Python. A subsequent narrow loader review timed out and is not claimed complete.
- Host validation passed for apply and restore. Seven writer test cases passed, including seven distinct prewrite-guard failures, six distinct write/readback failures with automatic rollback, partial-write undo and unrelated-change rejection; nine image-patch tests also passed. Fault injection runs POSIX shell with stub hardware commands: it is not a hardware/Hush execution test.
- Owner returned the frame to FEL. The first approved loader attempt initialized SPL, loaded/verified main U-Boot and uploaded the original boot image to RAM, but the 16 MiB RAM readback hit sunxi-tools' 10-second bulk-receive timeout. Main U-Boot was NEVER executed, patched payload/script were not uploaded, and no frame flash write occurred. The interrupted FEL read can leave the USB protocol waiting on unread data; another complete USB/DC power-cycle with the trigger card inserted is needed before retry. After UMS returns, re-identify disk number and run the Terminal verifier before removing SD/booting Android.
- Limitations: automatic rollback cannot survive power loss/reset/hard hang; use manual FEL restore afterward. CRC guards are integrity checks, not cryptographic authentication; host SHA/SID checks provide additional identity/integrity. Android/Frameo could later override USB/TCP properties; confirm actual ADB authorization and port state after normal boot.

### First load timeout and bounded-read fix

- First attempt report: `diagnostics/ms33-adb-patch/writer/fel-apply-1791862821170964000/report.json`; `execution_requested=false`, `flash_result=NOT_EXECUTED`.
- `sunxi-tools/fel_lib.c` bounds USB sends at 512 KiB but uses the entire requested length for a receive, with `USB_TIMEOUT=10000`. A 16 MiB receive timed out before any flash execution; subsequent USB commands may stall until power-cycle.
- Loader now requests RAM readback in <=512 KiB chunks, validates every exact length and hashes the complete range before execution. It journals `NOT_EXECUTED` before SPL and RAM verification progress after each payload. Flash execution remains the final explicit step only after all SHA-256 checks pass.
- Offline tests passed for full multi-chunk hashing, final partial chunk, exact length/short-read rejection, temporary-file cleanup, and host artifact validation. The approved boot image, guarded U-Boot binary, scripts and write ranges are unchanged.

### Bounded-read retry: execution requested, verification pending

- Owner power-cycled back into FEL and authorized retry. SID/SoC/helper/approved boot hashes matched.
- Loader successfully verified main U-Boot (475,360 bytes), complete original boot (16,777,216), complete approved patch (16,777,216) and apply script (1,319) via bounded RAM readback before executing main U-Boot.
- Retry report: `diagnostics/ms33-adb-patch/writer/fel-apply-1791863196788317000/report.json`; `execution_requested=true`, `flash_result=PENDING_TERMINAL_VERIFICATION`. Do NOT infer successful flash merely from helper execution.
- Read-only UMS returned: disk4, UMS disk 0, USB/external, 31,268,536,320 bytes, writable=false. Boot disk4s6 still offset 88,080,384, size 16,777,216, writable=false.
- Current active helper is the guarded writer, not the original read-only-only helper. USB host writes remain prohibited; only the two boot ranges were eligible for the scripted apply/automatic restore.
- Required next command in owner Terminal: `sudo /opt/homebrew/bin/python3 -I scripts/a33-uboot/verify-ms33-boot-macos.py disk4 31268536320 patched`. Keep both cables/card inserted until output confirms two exact matches. Re-identify disk number if disconnected.

### Full post-write verification passed; Android ADB pending

- Owner ran `verify-ms33-boot-macos.py disk4 31268536320 patched`. It verified the entire 16 MiB patched boot twice against the approved image, SHA-256 `0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33`, and the Android legacy image ID. Elapsed 26.88 seconds; `plan.json` now `applied=true`.
- First persistent boot change is CONFIRMED applied. Flash result is verified independently; originals/full recovery remain preserved. Kernel/recovery/system/userdata were not targeted by the guarded writer.
- Normal-boot instructions given: disconnect BOTH USB/DC, remove trigger microSD, reconnect USB then DC. Frameo is expected to remain the foreground/default app until a normal launcher is configured.
- Host ADB server is running. A 100-second watch saw no authorized device yet; subsequent USB/disk checks confirm the frame STILL runs read-only UMS (USB download gadget, VID 7994/PID 4112, disk4), so it has not returned to Android yet. Await owner disconnecting both power sources/removing FEL card/normal boot; do not infer a USB patch failure.

### Normal boot confirmed, ADB not yet available

- Owner confirms Frameo appeared. Read-only UMS is gone; normal USB inspection shows only the existing Mac hubs, with no frame USB device. `adb devices -l` remains empty.
- TCP 5555 at the frame's previous IP `192.168.1.24` returns connection refused; no network ADB connected.
- Next non-firmware diagnostic: Frameo Settings > Manage photos > Enable transfer from computer, toggle on (or off/on if already on), then hotplug USB ONLY while keeping DC connected. This activates the specifically patched mass_storage action plus renews USB connection detection. Await result before changing firmware again.
- Successful boot-image verification is not the same as successful Android USB/ADB access. No launcher, Settings, browser or WebView installation has happened yet.

### Photo-transfer toggle/hotplug also failed; kernel support checked offline

- Owner enabled/toggled photo transfer and hotplugged USB while DC stayed connected. Mac still sees no frame USB device; `adb devices` empty; TCP5555 at previous IP still refused. No further frame firmware change made.
- Extracted this unit's embedded `IKCFG_ST` gzip kernel config from its verified original boot image, saved privately to `diagnostics/ms33-kernel.config`. Kernel is an uncompressed ARM image, Linux 3.4.39, build #50 SMP PREEMPT Nov 17 2025.
- Confirmed compiled-in gadget support: `CONFIG_USB_GADGET=y`, `CONFIG_USB_SUNXI_UDC0=y`, `CONFIG_USB_G_ANDROID=y`, USB manager and USB0 OTG enabled. USB transport failure is not explained by an absent gadget driver; USB role/board configuration or runtime overrides remain possible. Do NOT infer their exact cause without runtime logs/FEX.
- Owner approved using temporary authenticated Wi-Fi/TCP ADB to diagnose and permanently repair normal Android USB. Offline transition is prepared and tested as described below. Run only on a trusted home network and never forward TCP 5555 externally.

### Temporary authenticated TCP-ADB transition (APPLIED AND VERIFIED)

- Transition source is the currently applied USB-ADB boot image, independently verified twice: SHA-256 `0f754612fd4a828068481e3d3e34875ef106f1a3e393bbbd12d5cd00d980ef33`. It is the automatic/manual rollback target—not the older stock image.
- Target: `diagnostics/ms33-tcp-adb-patch/tcp-adb-boot.img`, SHA-256 `b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe`.
- Exact ramdisk changes only: `default.prop` adds `ro.adb.secure=1`; `init.sun8i.usb.rc` replaces the prior no-TCP boot-completion action with port 5555 startup and restart actions if Android selects USB `none` or resets the TCP property to `-1`. Existing USB patch and `/adb_keys` record remain byte-for-byte unchanged. Kernel, recovery, system, adbd binary and SELinux policy unchanged; `ro.secure=1`, `ro.debuggable=0`; no root.
- Static inspection of this exact stripped adbd finds authentication code and both `/adb_keys` paths but no `ro.adb.secure` literal. Matching AOSP Android 6 source shows the literal is optimized out when `ALLOW_ADBD_NO_AUTH` is false, making RSA authentication unconditional; the added property is defensive. Runtime rejection of an unknown key is still not proven. `/data/misc/adb/adb_keys` could hold additional authorized keys and will be inspected after access.
- Offline builder: `scripts/a33-uboot/make-ms33-tcp-adb-patch.py`; transition plan: `diagnostics/ms33-tcp-adb-patch/plan.json`. Independent legacy Android/newc parser confirms only the two intended records differ, embedded Mac public-key token hash is unchanged, full in-memory apply/undo reconstructs exact images, and cpio validation passes.
- Guarded scripts: `scripts/a33-uboot/prepare-ms33-tcp-writer.py`; loader: `load-ms33-tcp-writer.py`; full twice-read verifier: `verify-ms33-tcp-boot-macos.py`. They reuse guarded U-Boot SHA `9eba32c640016a02d507e887a512ffc25068a0a74ed4e469769838cdab3f7f5a` and its exact range allowlist.
- Seven fault-injection writer tests passed: source mismatch/prewrite failure refusal, target success, six write/readback failure rollback paths, partial-image manual rollback and unrelated-byte rejection. Apply/restore host validation passed. Independent static audit found no blocking flash-path issue.
- Risks/limitations: TCP ADB binds broadly on trusted LAN; power loss during transition still needs FEL restore; host SHA validation precedes runtime CRC guards; data-partition ADB keys may authorize other clients. Remove TCP access after USB diagnosis/fix.
- Owner re-entered FEL. Exact A33/SID confirmed. Loader verified in RAM: guarded main U-Boot 475,360 bytes, complete verified USB-ADB base 16,777,216 bytes, complete TCP target 16,777,216 bytes, and apply script 1,283 bytes. Guarded apply execution requested; report `diagnostics/ms33-tcp-adb-patch/writer/fel-apply-1791865498181979000/report.json` remains pending independent verification.
- Read-only UMS returned as disk4 with exact whole-device and boot-partition geometry. Owner-Terminal verifier read the complete boot partition twice; both exactly match TCP target SHA-256 `b76a0ef59cdc1c908cb52b7b0137e87d0f234987bb989397e7c40c3fe425a3fe`; Android image ID valid. `plan.json` applied=true and execution report marked verified.
- Next: disconnect BOTH USB/DC, remove FEL card, reconnect USB then DC, await Frameo, connect only to trusted-LAN `192.168.1.24:5555`, verify device key authorization and collect runtime USB properties/sysfs/logs. Do not alter packages/settings until diagnostics are saved.

## Live USB diagnosis and permanent role correction (APPLIED AND VERIFIED)

- Trusted-LAN ADB connected at `192.168.1.24:5555`; runtime identity is M10R5, Android 6.0.1/API 23, ARM/Allwinner sun8i. Read-only runtime captures are in `diagnostics/ms33-runtime-*.txt`.
- Android's gadget layer was already enabled with ADB/PTP or MTP functions, but `/sys/class/android_usb/android0/state` stayed `DISCONNECTED`. The Allwinner USB manager reported OTG role `1`, and the Mac saw no frame.
- Matching Allwinner 3.4 driver source defines OTG roles as `0=NULL`, `1=HOST`, `2=DEVICE`. A RAM-only write of `2` briefly enumerated at high speed, then the old scanner completed one stale cycle and removed it. The driver loop checks its stop flag before a one-second sleep; a second `2` write after two seconds remains stable.
- This exact sequence was tested from a fresh reboot: initial role `1`/`DISCONNECTED`; `echo 2`, sleep two seconds, `echo 2`; role remained `2` and gadget `CONFIGURED` after 5 and 15 seconds. macOS enumerated VID:PID `1f3a:1007`, and USB ADB serial `a008acf7769700000000` worked.
- Security finding: this vendor `/sbin/adbd` does **not** enforce RSA authorization despite `ro.adb.secure=1`, `ro.secure=1`, `ro.debuggable=0`, the embedded `/adb_keys`, and no `/data/misc/adb/adb_keys` file. An isolated ADB server with fresh, distinct keys obtained both TCP and USB `device` transports; over USB it successfully ran `id` as unprivileged UID 2000 (`shell`). Do not describe either transport as authenticated. This is vendor-adbd behavior, not root access.
- Because temporary TCP had been approved only under the authentication assumption, it was disabled immediately in RAM: set `sys.boot_completed=0`, requested `adb usb`, and verified `service.adb.tcp.port=0`, port 5555 closed/refused, stable role `2`, and USB `CONFIGURED`. A reboot would restore the currently flashed temporary TCP actions; avoid reboot until the permanent transition is handled.
- Permanent candidate: `diagnostics/ms33-usb-role-patch/usb-role-boot.img`, SHA-256 `1cb468440e18ee7a914376ed890215bdf54a7c31ac5fcce797850291c7f0c1db`. It preserves the verified TCP image as transition base (`b76a0e…`), removes every TCP-ADB recovery action, sets the TCP port to `-1` before restarting adbd, adds one executable ramdisk helper, and selects DEVICE twice two seconds apart. Kernel, recovery, system, vendor adbd, SELinux policy, `default.prop`, and embedded key remain unchanged. It intentionally claims no authentication enforcement.
- Builder/test/writer/verifier: `make-ms33-usb-role-patch.py`, `test-ms33-usb-role-patch.py`, `prepare-ms33-usb-role-writer.py`, `test-ms33-usb-role-writer.py`, `load-ms33-usb-role-writer.py`, and `verify-ms33-usb-role-boot-macos.py`. Three image tests and seven writer fault-injection cases pass; check/apply/restore host validation passes.
- Guarded writes remained exactly the boot ramdisk sectors `[191892,201156)` followed by header sectors `[172032,172034)`, with complete source-image, unit SID/geometry/prefix, payload CRC/SHA, readback, full-image comparison, and automatic rollback guards. Owner approved and FEL identity matched. All four RAM payloads passed SHA-256 readback before execution. Read-only UMS then returned, and the complete boot partition independently matched target SHA-256 `1cb468440e18ee7a914376ed890215bdf54a7c31ac5fcce797850291c7f0c1db` twice; Android image ID valid.
- Runtime verification passed on the first normal cardless boot and two additional controlled cardless reboots. Each returned USB ADB automatically with role `2`, gadget `CONFIGURED`, adbd running, TCP property `-1`, and LAN port 5555 closed. Frameo may change functions from `adb` to `ptp,adb`; enumeration remains stable. Final capture: `diagnostics/ms33-permanent-usb-runtime.txt`.

## Launcher, browser and dashboard kiosk (INSTALLED AND VERIFIED)

- Before app changes, backed up and hashed Settings, WebView, the installed Frameo update, and the built-in Frameo system APK under `backups/ms33-apps-before-dashboard/`. Correct versions are Frameo data update `1.32.12 OTA test`/78071 and built-in `1.28.14`/58400. The update had already occurred before this stage.
- Existing system WebView is already ARMv7 `106.0.5249.126`/524912603, target API 33: the final Chromium generation compatible with Android 6/API 23. It is enabled and successfully renders the kiosk; no system/WebView replacement was needed.
- Installed F-Droid KISS Launcher `3.26.0`/224 (min API 21), APK SHA-256 `da6ab0b1219ad3b5ee573698523fb15d60a918083e0843f94a03c1b12e1098c9`. Optional contacts permission was denied with `USER_FIXED`. KISS works as a regular launcher and shows Settings, Home HQ, Lightning, and other apps.
- Installed F-Droid Lightning Browser `5.1.0`/101 (min API 19), APK SHA-256 `820f4f9977a20b060b4091db2b35cff8cd360e060f94aa742255c845747a2d7f`. It provides a conventional address bar/tabs and renders with the system WebView 106 engine.
- Copied the pinned reference kiosk from `wesbos/photo-frame-dashboard` commit `fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03` to `apps/ms33-homehq/`. Local changes make it a HOME activity, persist any HTTP/HTTPS VIEW URL for future boot launches, and make **Open launcher** prefer KISS while skipping Frameo. Build uses JDK 17, Android platform/build-tools 34, min/target API 23, and only requests Internet.
- Installed Home HQ `1.2-ms33`/3, APK SHA-256 `5b7b0a4f787ae84783199b3cd3f4ec11ffbc7c4031945b42893cf37a11557284`. Signature verification passed v1/v2/v3. Home HQ is the preferred HOME with `mAlways=true`; a cardless reboot confirms it starts full-screen automatically and loads the reference dashboard. Hold two fingers still for 1.5 seconds for launcher, Settings, or reload.
- Enabled the included `NavigationService` because this firmware lacks a navigation bar. It reads no accessibility events/content. Outside the dashboard, floating **Back** and **Dashboard** controls appear; the Dashboard control was tested. The service remains enabled after reboot.
- Frameo's privileged system status prevents shell or Settings from enabling the Disable button. Used Android's reversible **Force stop** instead. Frameo remains installed with its update/data preserved, and the active update initially stayed `stopped=true` across reboot. A later check found that the vendor had cleared the flag again without taking foreground; it was force-stopped again. This is best-effort suppression, not equivalent to Disable and not a security boundary. Home HQ remains the preferred HOME.
- Final post-install reboot: Home HQ resumed automatically, USB role `2`, gadget `CONFIGURED`, TCP property `-1`, and port 5555 closed. Install manifest: `diagnostics/ms33-dashboard-install.json`; final screenshot: `diagnostics/ms33-final-dashboard.png`.
- The kiosk currently uses the reference demo URL. Set and persist the owner's URL with: `adb shell am start -a android.intent.action.VIEW -d 'https://example.com/dashboard' -n com.wesbos.homehq/.MainActivity`.

## Presence/dimming assessment

- No built-in presence hardware was found: zero camera devices, no `/dev/video*`, no PIR/proximity/light sensor feature or sysfs node, and no IIO/hwmon sensor. Available sensors are only a Mi3da accelerometer and `sunxi-ths` board-temperature input; input devices are touchscreen, accelerometer, power key, temperature and headset keys.
- There is no standard `/sys/class/backlight` node. Android brightness is writable through Settings/Window APIs (current 204, range reported 75–255). The kiosk intentionally sets `FLAG_KEEP_SCREEN_ON`; system timeout is effectively infinite (`2147483647`).
- True nearby-person dimming therefore needs an external/network presence signal, such as Home Assistant/ESPHome PIR or mmWave. USB presence hardware would conflict with the port's forced DEVICE/ADB role; a network sensor is preferable. A simpler no-touch timer can be implemented in the kiosk, but that detects interaction, not nearby people.

## Sources

- https://wesbos.com/hacking-smart-photo-frames
- https://github.com/wesbos/photo-frame-dashboard
- https://divinehawk.github.io/2026/07/08/pastigio-frame-adb-fel-mode.html (same PCB ID, different chip marking; A33)
- https://divinehawk.github.io/2026/07/10/u-boot-adb-setup.html
- https://github.com/linux-sunxi/sunxi-tools
- https://github.com/wesbos/photo-frame-dashboard/issues/38 (newer MS33/ZC002 report: different eMMC capacities and firmware, fragile borrowed U-Boot, storage conservatively negotiated; do not copy its binary patch offsets)

The M10R7/FCC manual's Rockchip specifications did NOT match this frame. Match physical PCB and FEL query, not retail model alone. Published MS33 U-Boot is a useful reference, not an authenticated read-only payload; prefer a reproducible read-only build before exposing storage to macOS.
