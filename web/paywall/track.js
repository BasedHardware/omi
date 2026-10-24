// Web paywall analytics and version assignment, straight against PostHog (project 302298).
//
// Identity: the app passes the reader's PostHog `distinct_id` in the URL fragment (never sent to
// the server; kept for this webview session, then dropped from the address), so page events and the experiment
// exposure join the reader's own app events (`Upgrade Succeeded`, retention, ...). Without it
// (older app builds) events use an anonymous id kept on this device and create no person
// profile. A reader who turned product analytics off arrives with `analytics=off`: nothing is
// sent, and the version is picked locally.
//
// Delivery: every event is queued on the device first and removed only once PostHog accepts it;
// the queue is resent on the next load with the same uuid, which PostHog deduplicates, so an
// event cut off by the app closing the page is not lost.
(function () {
  var KEY = 'phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y';
  var HOST = 'https://us.i.posthog.com';
  var VERSION_FLAG_KEY = 'web-paywall-version';
  var QUEUE = 'omi_pw_queue';
  var q = new URLSearchParams(location.search);

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {}
    return null;
  }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 3) | 8).toString(16);
    });
  }
  function queue() {
    try { return JSON.parse(store(QUEUE) || '[]'); } catch (e) { return []; }
  }
  function save(list) { store(QUEUE, JSON.stringify(list.slice(-50))); }

  var enabled = q.get('analytics') !== 'off';
  var hash = new URLSearchParams(location.hash.slice(1));
  var appId = null;
  try {
    if (hash.get('distinct_id')) sessionStorage.setItem('omi_pw_did', hash.get('distinct_id'));
    appId = hash.get('distinct_id') || sessionStorage.getItem('omi_pw_did');
  } catch (e) { appId = hash.get('distinct_id'); }
  var deviceId = store('omi_pw_id');
  if (!deviceId) { deviceId = uuid(); store('omi_pw_id', deviceId); }
  var distinctId = appId || deviceId;

  // Assignment details handed over by index.html, then dropped from the visible URL.
  var assigned = q.get('_ps') || (q.get('v') ? 'preview' : 'direct');
  if (q.has('_ps') || q.has('_pv') || location.hash) {
    q.delete('_ps'); q.delete('_pv');
    try { history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q.toString() : '')); } catch (e) {}
  }

  var pageId = uuid();
  var started = Date.now();
  function num(key) { var v = q.get(key); return v == null ? null : parseInt(v, 10); }

  function post(event) {
    try {
      fetch(HOST + '/i/v0/e/', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(event), keepalive: true })
        .then(function (res) {
          if (!res.ok) return;
          save(queue().filter(function (e) { return e.uuid !== event.uuid; }));
        })
        .catch(function () {});
    } catch (e) {}
  }

  window.omiTrack = function (name, props) {
    if (!enabled) return;
    var version = window.OMI_PAYWALL_VERSION || 'router';
    var properties = {
      paywall_version: version,
      assignment: assigned,
      is_preview: assigned === 'preview',
      identified: !!appId,
      source: q.get('source'),
      platform: q.get('platform'),
      locale: q.get('locale'),
      tier: q.get('tier'),
      free_minutes: num('free_minutes'),
      year_amount: num('year_amount'),
      month_amount: num('month_amount'),
      currency: q.get('year_currency') || q.get('month_currency'),
      page_id: pageId,
      seconds_on_page: Math.round((Date.now() - started) / 100) / 10,
      $host: location.host,
      $current_url: location.origin + location.pathname,
      $lib: 'omi-web-paywall'
    };
    if (assigned === 'flag') properties['$feature/' + VERSION_FLAG_KEY] = version;
    if (!appId) properties.$process_person_profile = false;
    for (var k in props || {}) properties[k] = props[k];
    var event = { api_key: KEY, event: name, distinct_id: distinctId, properties: properties, timestamp: new Date().toISOString(), uuid: uuid() };
    var list = queue();
    list.push(event);
    save(list);
    post(event);
  };

  // The experiment exposure PostHog Experiments counts. Only for a real flag assignment.
  window.omiExposure = function () {
    if (assigned !== 'flag') return;
    var version = window.OMI_PAYWALL_VERSION;
    window.omiTrack('$feature_flag_called', { $feature_flag: VERSION_FLAG_KEY, $feature_flag_response: version });
  };

  // Asks PostHog which version this reader is in: the variant, `false` when the flag is off for
  // this reader, or null on any failure or timeout.
  window.omiVersionFlag = function (timeoutMs) {
    if (!enabled || !window.fetch) return Promise.resolve(null);
    var done = false;
    return new Promise(function (resolve) {
      var timer = setTimeout(function () { if (!done) { done = true; resolve(null); } }, timeoutMs);
      fetch(HOST + '/flags/?v=2', {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: JSON.stringify({ api_key: KEY, distinct_id: distinctId })
      })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
          var value = null;
          if (data && data.flags && !data.errorsWhileComputingFlags) {
            // An inactive (not yet launched) flag is left out of the answer: treat it as off.
            var flag = data.flags[VERSION_FLAG_KEY];
            value = flag && flag.enabled ? flag.variant : false;
          }
          if (!done) { done = true; clearTimeout(timer); resolve(typeof value === 'string' ? value : (value === false ? false : null)); }
        })
        .catch(function () { if (!done) { done = true; clearTimeout(timer); resolve(null); } });
    });
  };

  if (!enabled) { save([]); return; }

  window.addEventListener('error', function (e) {
    window.omiTrack('Web Paywall Error', { message: String(e.message || '').slice(0, 200), file: String(e.filename || '').split('/').pop() });
  });
  // When the app closes the page or the reader leaves it. Best effort: the app may tear the
  // webview down before this runs.
  var left = false;
  function leave(how) {
    if (left || !window.OMI_PAYWALL_VERSION) return;
    left = true;
    window.omiTrack('Web Paywall Left', { how: how, step: window.omiStep ? window.omiStep() : null });
  }
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') leave('hidden'); });
  window.addEventListener('pagehide', function () { leave('pagehide'); });

  // Resend anything an earlier visit could not deliver.
  queue().forEach(post);
})();
