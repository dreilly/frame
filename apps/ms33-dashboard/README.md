# MS33 custom dashboard

This is the editable web-app working copy for the Pastigio M10R5 frame.

## Provenance

Copied without web-source changes from `wesbos/photo-frame-dashboard/dashboard` at commit:

```text
fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03
```

The upstream Android `kiosk/` directory was deliberately excluded. This project uses the separately adapted and already-installed native shell in `../ms33-homehq/`. Web sources remain unchanged at handoff; `package-lock.json` was refreshed within the declared semver ranges to remove a development-only Wrangler dependency advisory.

## Device constraints

- Viewport: 1280×800 landscape.
- Android 6.0.1/API 23, ARMv7.
- Renderer: Android System WebView 106.0.5249.126.
- Keep the existing Vite targets (`chrome106` and conservative `chrome61` CSS) unless verified on the physical frame.
- This is an always-on wall display primarily viewed at a distance and touched occasionally.
- Never embed private service credentials in client-side JavaScript.

## Development

```sh
npm ci
npm run dev
```

At handoff, `npm audit` reports zero vulnerabilities and a clean production build succeeds with Vite 8.3.1 and Wrangler 4.150.0.

Production build:

```sh
npm run build
npm run preview
```

The inherited Cloudflare Workers deployment command is:

```sh
npm run deploy
```

Hosting and data integrations have not been selected yet. Before tailoring the app, gather requirements for content, services, design, interaction, privacy, refresh behavior, offline/error handling, and deployment.

See the repository root `README.md` for device state, ADB testing, and how to point Home HQ at a deployed URL.
