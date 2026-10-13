import { defineConfig, loadEnv } from 'vite';

// The wall tablet runs Android WebView 106 — keep JS output within Chromium 106.
// CSS targets chrome61 on purpose: the tablet's WebView rejects 4/8-digit hex colours (#0000,
// #ffffffbf) even though Chrome 106 should support them, and a newer target lets the minifier
// rewrite transparent/rgba() into that form. Verified on-device with CSS.supports().
const weatherProxy = {
  '/api/weather': {
    target: 'https://api.open-meteo.com',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api\/weather/, '/v1/forecast'),
  },
};

function calendarFeed(mode) {
  const { APPLE_CALENDAR_URL } = loadEnv(mode, process.cwd(), '');
  const middleware = async (req, res, next) => {
    if ((req.url || '').split('?')[0] !== '/api/calendar') return next();
    if (!APPLE_CALENDAR_URL) {
      res.statusCode = 503;
      return res.end('Calendar feed is not configured');
    }
    try {
      const url = APPLE_CALENDAR_URL.replace(/^webcal:/, 'https:');
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) throw new Error(`iCloud returned ${response.status}`);
      res.statusCode = 200;
      res.setHeader('Content-Type', 'text/calendar; charset=utf-8');
      res.setHeader('Cache-Control', 'private, max-age=300');
      res.end(await response.text());
    } catch (error) {
      res.statusCode = 502;
      res.end('Unable to load calendar feed');
    }
  };
  return {
    name: 'icloud-calendar-feed',
    configureServer(server) { server.middlewares.use(middleware); },
    configurePreviewServer(server) { server.middlewares.use(middleware); },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [calendarFeed(mode)],
  build: {
    target: 'chrome106',
    cssTarget: 'chrome61',
  },
  server: { host: true, proxy: weatherProxy },
  preview: { host: true, proxy: weatherProxy },
}));
