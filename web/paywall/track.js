// Web paywall analytics: sends events straight to PostHog (project 302298) with the version the
// reader is in. The page does not know who the reader is, so events use an anonymous id kept on
// this device, and no person profiles are created. Every event is queued on the device first and
// removed only once PostHog accepts it; the queue is resent on the next load with the same uuid,
// which PostHog deduplicates, so an event cut off by the app closing the page is not lost.
(function () {
  var KEY = 'phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y';
  var URL = 'https://us.i.posthog.com/i/v0/e/';
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

  var id = store('omi_pw_id');
  if (!id) { id = uuid(); store('omi_pw_id', id); }

  function post(event) {
    try {
      fetch(URL, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify(event), keepalive: true })
        .then(function (res) {
          if (!res.ok) return;
          save(queue().filter(function (e) { return e.uuid !== event.uuid; }));
        })
        .catch(function () {});
    } catch (e) {}
  }

  window.omiTrack = function (name, props) {
    var properties = {
      paywall_version: window.OMI_PAYWALL_VERSION || 'unknown',
      source: q.get('source'),
      platform: q.get('platform'),
      locale: q.get('locale'),
      tier: q.get('tier'),
      $host: location.host,
      $current_url: location.origin + location.pathname,
      $lib: 'omi-web-paywall',
      $process_person_profile: false
    };
    for (var k in props || {}) properties[k] = props[k];
    var event = { api_key: KEY, event: name, distinct_id: id, properties: properties, timestamp: new Date().toISOString(), uuid: uuid() };
    var list = queue();
    list.push(event);
    save(list);
    post(event);
  };

  // Resend anything an earlier visit could not deliver.
  queue().forEach(post);
})();
