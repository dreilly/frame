// Shared image helper + the hidden demo drawer.
(function () {
  'use strict';
  var $ = App.$;

  App.img = function (seed, w, h) {
    return 'https://picsum.photos/seed/' + seed + '/' + w + '/' + h;
  };

  function demoHTML() {
    var t = App.now();
    return '<div class="demo-panel">' +
      '<div class="demo-head"><div><div class="label label--light">Prototype</div><h2 class="serif">Demo controls</h2></div><button class="demo-x" data-demo-close>' + App.icon('x', 28) + '</button></div>' +
      '<div class="demo-sec"><div class="label label--light">Time of day · now ' + App.fmt.time(t) + '</div><div class="demo-grid">' +
      '<button data-time="7:10">7:10 AM</button><button data-time="15:18">3:18 PM</button><button data-time="19:45">7:45 PM</button><button data-time="23:40">11:40 PM</button><button data-time="real">Real time</button></div></div>' +
      '<div class="demo-sec"><div class="label label--light">Modes</div><div class="demo-grid">' +
      '<button data-mode="ambient">Ambient</button><button data-mode="night">Night</button><button data-fastidle>' + (App.idle.home < 60 ? 'Idle: fast ✓' : 'Idle: fast') + '</button></div></div>' +
      '<p class="demo-note">Keyboard: <b>D</b> demo · <b>A</b> ambient · <b>N</b> night · <b>1–5</b> views</p>' +
      '</div>';
  }

  App.openDemo = function () {
    var el = $('#demo');
    el.innerHTML = demoHTML();
    el.classList.add('is-open');
  };
  function closeDemo() { $('#demo').classList.remove('is-open'); }

  function demoClick(e) {
    var b = e.target.closest('button');
    if (!b) { if (e.target === $('#demo')) closeDemo(); return; }
    if (b.hasAttribute('data-demo-close')) return closeDemo();
    if (b.dataset.time) {
      if (b.dataset.time === 'real') App.setTime(null);
      else { var p = b.dataset.time.split(':'); App.setTime(+p[0], +p[1]); }
      App.openDemo();
      return;
    }
    if (b.dataset.mode) { closeDemo(); App.setMode(b.dataset.mode); return; }
    if (b.hasAttribute('data-fastidle')) {
      var fast = App.idle.home >= 60;
      App.idle.home = fast ? 8 : 60;
      App.idle.ambient = fast ? 15 : 120;
      App.openDemo();
      return;
    }
  }

  App.on('ready', function () {
    $('#demo').addEventListener('click', demoClick);
    App.hold($('#railClock'), 700, { done: App.openDemo });
    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT') return;
      var k = e.key.toLowerCase();
      if (k === 'd') { $('#demo').classList.contains('is-open') ? closeDemo() : App.openDemo(); }
      if (k === 'a') App.setMode('ambient');
      if (k === 'n') App.setMode('night');
      if (k === 'escape') { closeDemo(); App.closeSheet(); }
      var views = ['home', 'calendar', 'tasks', 'shopping', 'photos'];
      if (k >= '1' && k <= '5') App.go(views[+k - 1]);
    });
  });
})();
