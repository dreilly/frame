# Pastigio M10R5 Family Dashboard

A custom family dashboard and Android kiosk shell for the Pastigio M10R5 digital photo frame. The web app also runs in any modern desktop or tablet browser, so the dashboard can be developed without the frame.

## What is included

- `apps/ms33-dashboard/` — Vite dashboard and Cloudflare Worker
- `apps/ms33-homehq/` — Android HOME/WebView kiosk shell
- `docs/pastigio-m10r5.md` — detailed device, firmware, recovery, and installation history
- `scripts/a33-uboot/` — device-specific recovery and firmware verification tools; not needed for ordinary use

Private recovery material and generated files are intentionally excluded from Git. References to `backups/`, `diagnostics/`, or `downloads/` describe directories that may exist on the original development machine but will not be present in a normal clone.

## Fastest way to run the dashboard

Requirements:

- Git
- Node.js `20.19+` or `22.12+` (Node 22 LTS is recommended)
- npm

Clone the repository, install dependencies, and start Vite:

```sh
git clone <repository-url> frame
cd frame/apps/ms33-dashboard
npm ci
npm run dev
```

Open the URL printed by Vite. No frame, Apple calendar, Cloudflare account, or Android tooling is required for this first run. Without a configured calendar, the calendar panel shows an unavailable state while the other views continue to work.

The checked-in dashboard contains an example household and a Toms River, New Jersey weather configuration. Before regular use, customize:

1. Weather location in `apps/ms33-dashboard/js/config.js`.
2. Family members, colors, chores, shopping content, and photos in `apps/ms33-dashboard/js/data.js`.
3. The optional read-only calendar using an ignored `.env.local` file.

Full instructions are in [`apps/ms33-dashboard/README.md`](apps/ms33-dashboard/README.md).

## Production deployment

The included Cloudflare Worker serves the dashboard and proxies weather and calendar requests. From `apps/ms33-dashboard/`:

```sh
npx wrangler login
npx wrangler secret put APPLE_CALENDAR_URL
npm run deploy
```

The calendar secret is optional if calendar integration is not needed. Never commit calendar URLs, passwords, API tokens, or other credentials.

For LAN-only use, `npm run dev` or `npm run preview` can be used from a computer that remains available to the frame. For permanent use, deploy to Cloudflare or another host that provides equivalent same-origin API endpoints.

## Use it on the frame

The tested device configuration is:

- Pastigio M10R5, PCB MS33-V2.0, Allwinner A33
- Android 6.0.1/API 23 on ARMv7
- 1280×800 landscape display
- Android System WebView 106.0.5249.126
- Home HQ package `com.wesbos.homehq`

If Home HQ is already installed, set and persist the dashboard URL with ADB:

```sh
adb shell am start \
  -a android.intent.action.VIEW \
  -d 'https://example.com/dashboard' \
  -n com.wesbos.homehq/.MainActivity
```

Replace the example URL with the deployed URL or a reachable LAN URL. Do not include secrets in it. Home HQ reuses the URL after HOME launches and device restarts.

Hold two fingers still for 1.5 seconds inside Home HQ to open native controls for reloading the dashboard or opening Android apps and settings.

To build or install Home HQ on another device, follow [`apps/ms33-homehq/README.md`](apps/ms33-homehq/README.md). A new installation can generate its own signing key; updating an existing installation requires the same key that signed the installed APK.

## Device health check

Android platform tools are only required for frame installation and diagnostics. With the frame connected over USB:

```sh
adb devices -l
adb shell 'echo role=$(cat /sys/devices/platform/sunxi_usb_udc/otg_role) \
  usb=$(cat /sys/class/android_usb/android0/state) \
  tcp=$(getprop service.adb.tcp.port); \
  dumpsys activity activities | grep -m1 mResumedActivity'
```

The documented configuration reports one device, `role=2`, `usb=CONFIGURED`, and `tcp=-1`. When the dashboard is visible, the resumed activity is `com.wesbos.homehq/.MainActivity`.

## Security and privacy

- The published iCloud URL is a bearer credential. Keep it in `.env.local` or a deployment secret store.
- The calendar proxy exposes event details to anyone who can reach it. Keep the dashboard private or add access control before public deployment.
- Clear browser/WebView site data before transferring a configured device; weather and calendar responses are cached locally.
- The frame's vendor `adbd` does not enforce RSA client authorization. A computer physically connected over USB can obtain an unprivileged Android shell.
- Network ADB is disabled in the documented frame configuration.
- Recovery images, signing keys, diagnostic captures, and other private artifacts should not be added to Git.

## Device-specific recovery

Normal dashboard work does not require root access, firmware changes, FEL mode, or the scripts in `scripts/a33-uboot/`. Those tools are specific to the documented hardware and can make a device unbootable if used incorrectly.

For the complete conversion and recovery record, see [`docs/pastigio-m10r5.md`](docs/pastigio-m10r5.md).

## Hardware limitations

The tested frame has no usable PIR, proximity sensor, light sensor, camera, or standard backlight interface. Presence-aware dimming requires an external network source such as Home Assistant, an ESPHome PIR, or an mmWave sensor.
