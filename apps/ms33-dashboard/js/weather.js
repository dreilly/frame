// Live weather from Open-Meteo. Location settings live in config.js.
(function () {
  'use strict';
  var D = window.DATA;
  var W = window.DASHBOARD_CONFIG.weather;
  var CACHE_KEY = 'homehq-weather-v2-' + [W.latitude, W.longitude, W.timezone, W.temperatureUnit].join('-');
  var REFRESH_MS = 30 * 60 * 1000;
  var MAX_CACHE_AGE = 6 * 60 * 60 * 1000;
  var API_URL = '/api/weather' +
    '?latitude=' + encodeURIComponent(W.latitude) + '&longitude=' + encodeURIComponent(W.longitude) +
    '&current=temperature_2m,apparent_temperature,weather_code,is_day' +
    '&hourly=temperature_2m,precipitation_probability,weather_code,is_day' +
    '&daily=temperature_2m_max,temperature_2m_min' +
    '&temperature_unit=' + encodeURIComponent(W.temperatureUnit) +
    '&timezone=' + encodeURIComponent(W.timezone) +
    '&forecast_days=2';

  function round(n) { return Math.round(Number(n)); }

  function normalize(json) {
    if (!json.current || !json.hourly || !json.daily) throw new Error('Incomplete weather response');
    var currentHour = json.current.time.slice(0, 13) + ':00';
    var currentIndex = json.hourly.time.indexOf(currentHour);
    var hourly = json.hourly.time.map(function (time, i) {
      return {
        time: new Date(time).getTime(),
        temp: round(json.hourly.temperature_2m[i]),
        p: round(json.hourly.precipitation_probability[i] || 0),
        code: Number(json.hourly.weather_code[i]),
        isDay: !!json.hourly.is_day[i]
      };
    });
    return {
      location: W.location, status: 'live', updatedAt: Date.now(),
      current: {
        time: new Date(json.current.time).getTime(),
        temp: round(json.current.temperature_2m),
        feels: round(json.current.apparent_temperature),
        p: currentIndex >= 0 ? round(json.hourly.precipitation_probability[currentIndex] || 0) : 0,
        code: Number(json.current.weather_code),
        isDay: !!json.current.is_day
      },
      hourly: hourly,
      hi: round(json.daily.temperature_2m_max[0]),
      lo: round(json.daily.temperature_2m_min[0])
    };
  }

  function publish(weather) {
    D.weather = weather;
    App.emit('data');
  }

  function readCache() {
    try {
      var cached = JSON.parse(localStorage.getItem(CACHE_KEY));
      if (!cached || !cached.current || Date.now() - cached.updatedAt > MAX_CACHE_AGE) return null;
      cached.status = 'cached';
      return cached;
    } catch (e) { return null; }
  }

  function saveCache(weather) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(weather)); } catch (e) {}
  }

  function refresh() {
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 12000);
    fetch(API_URL, { cache: 'no-store', credentials: 'omit', signal: controller.signal })
      .then(function (response) {
        if (!response.ok) throw new Error('Weather request failed: ' + response.status);
        return response.json();
      })
      .then(function (json) {
        var weather = normalize(json);
        saveCache(weather);
        publish(weather);
      })
      .catch(function () {
        if (!D.weather.current) publish({
          location: W.location, status: 'error', updatedAt: null,
          current: null, hourly: [], hi: null, lo: null
        });
      })
      .then(function () { clearTimeout(timeout); });
  }

  var cached = readCache();
  if (cached) publish(cached);
  refresh();
  setInterval(refresh, REFRESH_MS);
})();
