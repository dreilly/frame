// Cloudflare Worker entry: serve the static dashboard and proxy Open-Meteo.
// The proxy keeps weather requests same-origin for the frame's older Android WebView.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== 'GET' && url.pathname.startsWith('/api/')) {
      return new Response('Method not allowed', { status: 405 });
    }

    if (url.pathname === '/api/weather') {
      const upstream = new URL('https://api.open-meteo.com/v1/forecast');
      url.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));
      const response = await fetch(upstream, { cf: { cacheTtl: 900, cacheEverything: true } });
      const headers = new Headers(response.headers);
      headers.set('Cache-Control', 'public, max-age=900');
      return new Response(response.body, { status: response.status, headers });
    }

    if (url.pathname === '/api/calendar') {
      if (!env.APPLE_CALENDAR_URL) return new Response('Calendar feed is not configured', { status: 503 });
      const upstream = env.APPLE_CALENDAR_URL.replace(/^webcal:/, 'https:');
      const response = await fetch(upstream, { cf: { cacheTtl: 300, cacheEverything: true } });
      const headers = new Headers(response.headers);
      headers.set('Content-Type', 'text/calendar; charset=utf-8');
      headers.set('Cache-Control', 'private, max-age=300');
      return new Response(response.body, { status: response.status, headers });
    }

    return env.ASSETS.fetch(request);
  },
};
