# Pastigio M10R5 dashboard project — session handoff

This directory is sufficient to continue the project locally. The frame conversion is complete and stable; future work should focus on the web dashboard, not firmware.

## Start the next session here

Tell the next coding session:

> Read `README.md`, then work only on tailoring `apps/ms33-dashboard/`. The frame and native kiosk are already stable. Do not change firmware, boot images, USB roles, or ADB configuration unless I explicitly start a separate repair task.

For dashboard design, begin by asking the owner what information, integrations, visual style, navigation, privacy model, and hosting target they want. Do not assume the demo family's data or services.

## Current stable state

- Pastigio M10R5 / PCB MS33-V2.0 / Allwinner A33.
- Android 6.0.1, API 23, ARMv7, 1280×800 landscape.
- System WebView `106.0.5249.126` renders the dashboard correctly.
- `Home HQ` (`com.wesbos.homehq`, `1.2-ms33`) is the persistent default HOME and starts full-screen after reboot.
- KISS Launcher `3.26.0`, Android Settings, and Lightning Browser `5.1.0` are available.
- Hold two fingers still for 1.5 seconds in Home HQ to open its native controls.
- Outside Home HQ, floating **Back** and **Dashboard** controls provide navigation.
- Frameo remains installed with data preserved and Home HQ owns HOME. The active Frameo update is currently force-stopped, but the vendor blocks a true disable and later cleared this flag once without taking foreground; treat force-stop as best-effort, not a security boundary.
- USB ADB automatically reaches role `2` / `CONFIGURED` after reboot.
- Network ADB is disabled (`service.adb.tcp.port=-1`); TCP 5555 was confirmed closed.
- Important security limitation: vendor `adbd` does not enforce RSA client authorization. Any computer physically connected by USB can obtain an unprivileged Android `shell` session. ADB is not root.
- The currently persisted kiosk URL is the Wes Bos reference demo. Custom URL selection is intentionally pending.

No FEL card, firmware operation, root, or Android-system modification is needed for normal web-app development.

## Project map

- `apps/ms33-dashboard/` — **start here for the custom web app**. Clean working copy of the upstream Vite dashboard at pinned commit `fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03`; native kiosk sources are intentionally separate.
- `apps/ms33-homehq/` — installed native Android WebView/HOME shell and navigation overlay. Change only if the web app genuinely needs a new native capability.
- `docs/pastigio-m10r5.md` — detailed chronological hardware, backup, firmware, Android, and installation record. The final-state sections near the end supersede earlier progress snapshots.
- `scripts/a33-uboot/` — recovery/verification tooling. Not needed for dashboard work.
- `backups/` — private firmware/APK recovery material and the preserved Home HQ update-signing key; intentionally ignored. Do not publish. The installed APK and saved key share signer certificate SHA-256 `68845378f8ac8296516e39894292405f1f0f7101bcb1c805fbeba4a089474172`.
- `diagnostics/` — private captures, build trees, screenshots, and the pinned upstream clone; intentionally ignored. Do not publish.
- `downloads/` — downloaded APK installers; not needed for web development.
- `diagnostics/ms33-dashboard-install.json` — machine-readable installed-app/final-runtime summary.

The root directory is **not yet a Git repository**. Initialize a private repository before substantial dashboard changes if desired. Review ignored/private material before publishing anything. Host dependencies (ADB/platform-tools, JDK 17, Android SDK/build-tools 34, Node/npm, and optional Cloudflare credentials) remain installed outside this directory; source, recovery data, and the native app's required signing identity are preserved here.

## Dashboard development

Requirements: Node.js/npm. The app is Vite-based and already targets Chrome/WebView 106 (`chrome106`; conservative `chrome61` CSS output).

```sh
cd apps/ms33-dashboard
npm ci
npm run dev
```

Vite listens on the host network. Open the printed Mac LAN URL in a normal browser or point Home HQ at it during device testing. Do not put API secrets directly in browser JavaScript; use a server/Worker and local environment variables.

Build and preview:

```sh
npm run build
npm run preview
```

Cloudflare Workers deployment exists upstream:

```sh
npm run deploy
```

Do not enter account passwords, API tokens, private calendar URLs, or other credentials into chat or commit them. Create ignored local environment files and provide sanitized `.env.example` names when integrations are designed.

## Point Home HQ at a URL

After the custom app is hosted or reachable on the LAN:

```sh
adb shell am start \
  -a android.intent.action.VIEW \
  -d 'https://example.com/dashboard' \
  -n com.wesbos.homehq/.MainActivity
```

Home HQ persists that URL across HOME launches and reboots. Avoid URLs containing secrets; if one is unavoidable, run the command yourself locally rather than sharing it in chat.

## Quick health check

With the frame connected over USB:

```sh
adb devices -l
adb shell 'echo role=$(cat /sys/devices/platform/sunxi_usb_udc/otg_role) \
  usb=$(cat /sys/class/android_usb/android0/state) \
  tcp=$(getprop service.adb.tcp.port); \
  dumpsys activity activities | grep -m1 mResumedActivity'
```

Expected: one device, `role=2`, `usb=CONFIGURED`, `tcp=-1`, and resumed activity `com.wesbos.homehq/.MainActivity`.

## Presence/dimming limitation

The frame has no PIR, proximity/light sensor, usable camera, or `/sys/class/backlight` interface. True nearby-person dimming requires a network presence source such as Home Assistant/ESPHome PIR or mmWave. A no-touch timer can be added to the kiosk, but it does not detect nearby people. Decide this separately after the dashboard requirements are known.
