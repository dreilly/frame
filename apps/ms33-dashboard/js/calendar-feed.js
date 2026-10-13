// Read-only iCloud calendar sync. The private feed URL stays in the server environment.
import ICAL from 'ical.js';

(function () {
  'use strict';
  var D = window.DATA;
  var CACHE_KEY = 'homehq-calendar-v2';
  var REFRESH_MS = 5 * 60 * 1000;
  var MAX_CACHE_AGE = 24 * 60 * 60 * 1000;
  var PAST_DAYS = 90;
  var FUTURE_DAYS = 400;
  var sourcePerson = D.people.filter(function (person) {
    return person.calendars && person.calendars.some(function (calendar) { return calendar.endpoint === '/api/calendar'; });
  })[0];
  var ownerId = sourcePerson ? sourcePerson.id : 'family';

  D.events = [];

  function toRecord(event, start, end, id) {
    if (event.component.getFirstPropertyValue('status') === 'CANCELLED') return null;
    return {
      id: 'ical-' + id,
      title: event.summary || 'Untitled event',
      start: start.toJSDate(),
      end: end.toJSDate(),
      allDay: !!start.isDate,
      people: [ownerId],
      loc: event.location || '',
      notes: event.description || ''
    };
  }

  function parseCalendar(source) {
    ICAL.TimezoneService.reset();
    var root = new ICAL.Component(ICAL.parse(source));
    root.getAllSubcomponents('vtimezone').forEach(function (zone) {
      ICAL.TimezoneService.register(zone);
    });

    var components = root.getAllSubcomponents('vevent');
    var exceptions = {};
    components.forEach(function (component) {
      if (!component.hasProperty('recurrence-id')) return;
      var uid = component.getFirstPropertyValue('uid');
      (exceptions[uid] = exceptions[uid] || []).push(component);
    });

    var startLimit = new Date();
    startLimit.setDate(startLimit.getDate() - PAST_DAYS);
    var endLimit = new Date();
    endLimit.setDate(endLimit.getDate() + FUTURE_DAYS);
    var records = [], id = 0;

    components.forEach(function (component) {
      if (component.hasProperty('recurrence-id')) return;
      var uid = component.getFirstPropertyValue('uid');
      var event = new ICAL.Event(component, { exceptions: exceptions[uid] || [], strictExceptions: true });
      if (event.component.getFirstPropertyValue('status') === 'CANCELLED') return;

      if (!event.isRecurring()) {
        var single = toRecord(event, event.startDate, event.endDate, id++);
        if (single && single.end > startLimit && single.start < endLimit) records.push(single);
        return;
      }

      var iterator = event.iterator(), occurrence, guard = 0;
      while ((occurrence = iterator.next()) && guard++ < 10000) {
        if (occurrence.toJSDate() >= endLimit) break;
        var details = event.getOccurrenceDetails(occurrence);
        var record = toRecord(details.item, details.startDate, details.endDate, id++);
        if (record && record.end > startLimit && record.start < endLimit) records.push(record);
      }
    });

    records.sort(function (a, b) { return a.start - b.start || a.end - b.end; });
    return records;
  }

  function publish(events, status, updatedAt) {
    D.events = events;
    D.calendar.status = status;
    D.calendar.updatedAt = updatedAt || null;
    App.emit('data');
  }

  function readCache() {
    try {
      var cached = JSON.parse(localStorage.getItem(CACHE_KEY));
      if (!cached || !Array.isArray(cached.events) || Date.now() - cached.updatedAt > MAX_CACHE_AGE) return null;
      cached.events.forEach(function (event) {
        event.start = new Date(event.start);
        event.end = new Date(event.end);
        event.people = [ownerId];
      });
      return cached;
    } catch (e) { return null; }
  }

  function saveCache(events, updatedAt) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ events: events, updatedAt: updatedAt })); } catch (e) {}
  }

  function refresh() {
    fetch('/api/calendar', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('Calendar request failed: ' + response.status);
        return response.text();
      })
      .then(function (source) {
        var events = parseCalendar(source), updatedAt = Date.now();
        saveCache(events, updatedAt);
        publish(events, 'live', updatedAt);
      })
      .catch(function () {
        if (!D.calendar.updatedAt) publish([], 'error', null);
      });
  }

  var cached = readCache();
  if (cached) publish(cached.events, 'cached', cached.updatedAt);
  refresh();
  setInterval(refresh, REFRESH_MS);
  window.addEventListener('online', refresh);
})();
