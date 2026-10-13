# MS33 Family Dashboard

A touch-friendly family dashboard for a 1280×800 wall display. It includes Today, Calendar, Chores, Shopping, Photos, ambient, and night views.

The dashboard is a Vite web app. Open-Meteo weather and a read-only iCloud calendar are routed through same-origin endpoints so they work in the frame's Android WebView.

## Requirements

- Node.js `20.19+` or `22.12+` (Node 22 LTS is recommended)
- npm
- Optional: a published iCloud calendar URL
- Optional: a Cloudflare account for deployment

## Quick start

From this directory:

```sh
npm ci
npm run dev
```

Open the local URL printed by Vite. The server listens on the host network, so another device on the same LAN can use the printed network URL.

A calendar is not required to run the app. Without one, the calendar area displays an unavailable state while the rest of the dashboard continues to work.

Available commands:

- `npm run dev` starts the development server.
- `npm run build` creates a production build in `dist/`.
- `npm run preview` serves the production build locally.
- `npm run deploy` builds and deploys with Wrangler.

## First-time customization

The checked-in data is an example household configuration. Update it before using the dashboard for another family.

### Weather

Edit `js/config.js` and set:

- `location` to the display label
- `latitude` and `longitude` to the forecast coordinates
- `timezone` to an IANA timezone such as `America/New_York`
- `temperatureUnit` to `fahrenheit` or `celsius`

Open-Meteo requires no API key. Weather refreshes every 30 minutes and the last successful response is cached in local storage for up to six hours. The cache is keyed by the weather configuration, so changing location does not reuse the previous location's forecast.

### Family and content

Edit `js/data.js` to customize:

- `people`, including IDs, names, colors, and calendar ownership
- chores, routines, and star totals
- stores, groceries, and shopping suggestions
- photo metadata and placeholder image seeds

Person IDs are referenced by chores, photos, and calendar events. If an ID changes, update all references to that ID in `js/data.js`.

Chore and shopping interactions are held in browser memory and reset when the page reloads; there is no synchronization backend.

### Apple Calendar

The calendar integration reads one published iCloud feed through `/api/calendar`. Events are read-only, refresh every five minutes, support recurring events and calendar time zones, and are cached in local storage for up to 24 hours.

To publish a calendar in Apple Calendar, open its sharing settings, enable **Public Calendar**, and copy the resulting `webcal://` URL. Anyone with that URL can read the calendar, so treat it as a secret and revoke sharing if it is exposed.

Associate `/api/calendar` with the correct person in that person's `calendars` array in `js/data.js`. For local development, copy the example environment file:

```sh
cp .env.example .env.local
```

Then replace the placeholder in `.env.local`:

```dotenv
APPLE_CALENDAR_URL=webcal://example.icloud.com/published/replace-with-private-token
```

`.env.local` is ignored by Git. Never put the real URL in `js/`, commit it, or pass it to the browser. If a browser previously loaded a different calendar, clear that site's local storage before handing the device to someone else.

## Deployment

The included Cloudflare Worker serves the static build and provides `/api/weather` and `/api/calendar`.

Authenticate Wrangler, configure the calendar secret, and deploy:

```sh
npx wrangler login
npx wrangler secret put APPLE_CALENDAR_URL
npm run deploy
```

The secret command prompts for the value without adding it to the repository. If calendar support is not needed, deployment can proceed without the secret; `/api/calendar` will return a configuration error.

The calendar endpoint returns private event details to anyone who can access it. Keep the deployment private or add access control before exposing it publicly.

On another hosting platform, provide equivalent same-origin `GET /api/weather` and `GET /api/calendar` endpoints or adapt the client integrations.

## Frame compatibility

The target frame runs Android 6.0.1/API 23 with Android System WebView 106 at 1280×800 in landscape orientation.

- Keep the Vite JavaScript target at `chrome106` unless a newer renderer is installed.
- Keep the conservative `chrome61` CSS target unless changes are tested on the physical frame.
- Design for an always-on display viewed at a distance and touched occasionally.
- Never include credentials or private feeds in browser-delivered assets.

See the repository root `README.md` for device setup and `../ms33-homehq/README.md` for the Android kiosk shell.

## Troubleshooting

- **Calendar unavailable:** confirm `.env.local` exists, restart Vite after changing it, and verify the calendar is still publicly shared.
- **Weather unavailable:** verify the coordinates and timezone in `js/config.js`, then check that `/api/weather` is reachable.
- **Old data remains visible:** clear site data/local storage in the browser or WebView and reload.
- **The frame cannot open the dev server:** use Vite's network URL, keep both devices on the same LAN, and allow the port through the development computer's firewall.

## Origin

This app began as the dashboard from `wesbos/photo-frame-dashboard` at commit `fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03`. The Android shell is maintained separately in `../ms33-homehq/`.
