# MS33 Family Dashboard

A touch-friendly family dashboard built for a 1280×800 wall-mounted Android frame. It provides Today, Calendar, Chores, Shopping, and Photos views, along with ambient and night display modes.

The app uses the device clock, live Open-Meteo weather, and a read-only published iCloud calendar. Weather and calendar responses are served through same-origin endpoints for compatibility with the frame's older Android WebView.

## Requirements

- Node.js and npm
- A published iCloud calendar URL for calendar sync
- A Cloudflare account only when deploying with Wrangler

## Local development

Install dependencies and create the local configuration file:

```sh
npm ci
cp .env.example .env.local
```

Set `APPLE_CALENDAR_URL` in `.env.local` to the private published `webcal://` URL, then start Vite:

```sh
npm run dev
```

Vite listens on the host network, so the dashboard can be opened from a browser or the frame using the printed LAN URL.

Other available commands:

- `npm run build` creates a production build in `dist/`.
- `npm run preview` serves the production build locally.
- `npm run deploy` builds and deploys the dashboard with Wrangler.

## Configuration

### Family and dashboard content

Family members, colors, calendar ownership, chores, shopping data, and photo metadata are defined in `js/data.js`. Calendar sources are associated with individual people through their `calendars` arrays.

Most interactive chore and shopping changes are local to the running browser and are not synchronized to a backend.

### Weather

Current conditions and the hourly forecast come from the free, keyless Open-Meteo API. Location coordinates, units, timezone, refresh interval, and cache lifetime are configured in `js/weather.js`.

The client refreshes weather every 30 minutes and keeps the last successful response in local storage for up to six hours. Development requests are proxied by Vite; deployed requests are proxied by `worker.js` at `/api/weather`.

### Apple Calendar

The dashboard reads a published iCloud calendar through `/api/calendar`. Calendar events are read-only, refreshed every five minutes, and cached in local storage for up to 24 hours. Recurring events and calendar time zones are parsed with `ical.js`.

For local development, place the feed URL in the ignored `.env.local` file:

```dotenv
APPLE_CALENDAR_URL=webcal://example.icloud.com/published/replace-with-private-token
```

For Cloudflare deployment, store it as a Worker secret:

```sh
npx wrangler secret put APPLE_CALENDAR_URL
```

Never commit the real calendar URL or expose it in client-side JavaScript. The calendar endpoint returns private event data to anyone who can access the dashboard, so keep the deployment private or add access control before making it publicly reachable.

## Deployment

The included Cloudflare Worker serves the static Vite build and provides the weather and calendar proxy endpoints. After configuring `APPLE_CALENDAR_URL`, deploy with:

```sh
npm run deploy
```

To use another hosting platform, provide equivalent same-origin `GET /api/weather` and `GET /api/calendar` endpoints or update the client integrations accordingly.

## Frame compatibility

The target frame runs Android 6.0.1/API 23 with Android System WebView 106 at 1280×800 in landscape orientation.

- Keep the Vite JavaScript target at `chrome106` unless a newer renderer is installed on the frame.
- Keep the conservative `chrome61` CSS target unless changes are verified on the physical device.
- Design for an always-on display viewed at a distance and touched occasionally.
- Do not place credentials, private feed URLs, or other secrets in browser-delivered assets.

See the repository root `README.md` for frame setup, ADB testing, and configuring the Home HQ shell to open a deployed dashboard URL.

## Origin

This app began as the dashboard from `wesbos/photo-frame-dashboard` at commit `fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03`. The upstream Android kiosk is not included; this repository uses the separate native shell in `../ms33-homehq/`.
