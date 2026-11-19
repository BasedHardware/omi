/* Pipeline lab inspector UI. Plain JS, no dependencies, no build step.
   Views: #/run/<run>  (day), #/run/<run>/c/<id>  (replay conversation), #/run/<run>/p/<id>  (production only),
   #/verdicts. All content is inserted as text nodes, never as HTML. */
'use strict';

(function () {
  // ---------------------------------------------------------------- utilities

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'style') el.style.cssText = v;
        else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
        else if (k === 'dataset') Object.assign(el.dataset, v);
        else el.setAttribute(k, v === true ? '' : String(v));
      }
    }
    append(el, kids);
    return el;
  }
  function append(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem('plab.' + key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
    },
    set(key, value) { try { localStorage.setItem('plab.' + key, JSON.stringify(value)); } catch (e) { /* private mode */ } },
  };

  async function getJSON(path) {
    const res = await fetch(path, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) { const err = new Error(body.error || res.statusText); err.status = res.status; throw err; }
    return body;
  }
  async function postJSON(path, data) {
    const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || res.statusText);
    return body;
  }

  let toastTimer = 0;
  function toast(msg, isError) {
    const el = $('#toast');
    el.textContent = msg;
    el.className = 'show' + (isError ? ' err' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = ''; }, isError ? 4000 : 1600);
  }

  // ---------------------------------------------------------------- time

  let TZ = 'UTC';
  const fmtCache = new Map();
  function fmt(opts) {
    const key = TZ + JSON.stringify(opts);
    if (!fmtCache.has(key)) {
      try { fmtCache.set(key, new Intl.DateTimeFormat('en-GB', Object.assign({ timeZone: TZ }, opts))); } catch (e) { fmtCache.set(key, new Intl.DateTimeFormat('en-GB', opts)); }
    }
    return fmtCache.get(key);
  }
  const ms = (iso) => (iso ? Date.parse(iso) : NaN);
  const clock = (iso) => (iso ? fmt({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(iso)) : '—');
  function dur(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return '—';
    const s = Math.round(seconds);
    if (s < 60) return s + 's';
    const m = Math.round(s / 60);
    if (m < 60) return m + 'm';
    return Math.floor(m / 60) + 'h ' + String(m % 60).padStart(2, '0') + 'm';
  }
  function mmss(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }
  function longDate(date) {
    if (!date) return 'Unknown day';
    const d = new Date(date + 'T12:00:00Z');
    return new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(d);
  }
  const usd = (v) => (typeof v === 'number' ? '$' + (v < 0.1 && v > 0 ? v.toFixed(4) : v.toFixed(2)) : '—');

  // ---------------------------------------------------------------- word diff

  function tokens(text) { return (text || '').match(/\S+\s*/g) || []; }

  /* Diff two token lists. Returns ops [{t:'eq'|'del'|'ins', s, a, b}] with indices into A (old) and B (new). */
  function diffTokens(A, B) {
    const ka = A.map((x) => x.trim()), kb = B.map((x) => x.trim());
    const ops = [];
    let pre = 0;
    while (pre < A.length && pre < B.length && ka[pre] === kb[pre]) { ops.push({ t: 'eq', s: B[pre], a: pre, b: pre }); pre++; }
    let suf = 0;
    while (suf < A.length - pre && suf < B.length - pre && ka[A.length - 1 - suf] === kb[B.length - 1 - suf]) suf++;
    const n = A.length - pre - suf, m = B.length - pre - suf;
    if (n && m && n * m <= 4e6) {
      const w = m + 1, dp = new Uint32Array((n + 1) * w);
      for (let i = n - 1; i >= 0; i--) {
        for (let j = m - 1; j >= 0; j--) {
          dp[i * w + j] = ka[pre + i] === kb[pre + j] ? dp[(i + 1) * w + j + 1] + 1 : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
        }
      }
      let i = 0, j = 0;
      while (i < n && j < m) {
        if (ka[pre + i] === kb[pre + j]) { ops.push({ t: 'eq', s: B[pre + j], a: pre + i, b: pre + j }); i++; j++; }
        else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) { ops.push({ t: 'del', s: A[pre + i], a: pre + i, b: -1 }); i++; }
        else { ops.push({ t: 'ins', s: B[pre + j], a: -1, b: pre + j }); j++; }
      }
      for (; i < n; i++) ops.push({ t: 'del', s: A[pre + i], a: pre + i, b: -1 });
      for (; j < m; j++) ops.push({ t: 'ins', s: B[pre + j], a: -1, b: pre + j });
    } else {
      for (let i = 0; i < n; i++) ops.push({ t: 'del', s: A[pre + i], a: pre + i, b: -1 });
      for (let j = 0; j < m; j++) ops.push({ t: 'ins', s: B[pre + j], a: -1, b: pre + j });
    }
    for (let k = suf; k > 0; k--) ops.push({ t: 'eq', s: B[B.length - k], a: A.length - k, b: B.length - k });
    return ops;
  }

  /* One side of a split diff: 'new' shows eq + ins, 'old' shows eq + del. Adjacent runs are merged. */
  function diffSide(oldText, newText, side) {
    const ops = diffTokens(tokens(oldText), tokens(newText));
    const out = [];
    let run = null, runText = '';
    const flush = () => {
      if (!runText) return;
      out.push(run === 'eq' ? runText : h(run === 'ins' ? 'ins' : 'del', null, runText));
      runText = '';
    };
    for (const op of ops) {
      if ((side === 'new' && op.t === 'del') || (side === 'old' && op.t === 'ins')) continue;
      if (op.t !== run) { flush(); run = op.t; }
      runText += op.s;
    }
    flush();
    return out;
  }

  // ---------------------------------------------------------------- state

  const state = {
    runs: null,
    overview: new Map(),
    dayPanel: new Map(),
    detail: new Map(),
    filters: store.get('filters', { changed: false, discarded: false, verdict: false, pushes: false }),
    search: '',
    selected: new Map(), // run -> conversation key selected on the day page
    tab: store.get('tab', 'summary'),
    trMode: 'replay',
    follow: store.get('follow', true),
    fit: store.get('fit', 'day'),
    rate: store.get('rate', 1),
    route: null,
    targets: [], // verdict targets on the current page, in focus order for the open tab
    focus: 0,
    renderToken: 0,
  };

  function convKey(row) { return (row.kind === 'production' ? 'p:' : 'c:') + row.id; }
  function convHref(runId, row) { return '#/run/' + encodeURIComponent(runId) + (row.kind === 'production' ? '/p/' : '/c/') + encodeURIComponent(row.id); }

  async function loadRuns(force) {
    if (!state.runs || force) state.runs = (await getJSON('/api/runs')).runs;
    return state.runs;
  }
  async function loadOverview(runId, force) {
    if (!state.overview.has(runId) || force) state.overview.set(runId, await getJSON('/api/runs/' + encodeURIComponent(runId)));
    return state.overview.get(runId);
  }
  async function loadDetail(runId, kind, id) {
    const key = runId + '|' + kind + '|' + id;
    if (!state.detail.has(key)) {
      const base = '/api/runs/' + encodeURIComponent(runId);
      state.detail.set(key, getJSON(base + (kind === 'production' ? '/production/' : '/conversations/') + encodeURIComponent(id)).catch((err) => {
        state.detail.delete(key);
        throw err;
      }));
    }
    return state.detail.get(key);
  }

  // ---------------------------------------------------------------- theme

  function applyTheme(theme) {
    if (theme === 'light' || theme === 'dark') document.documentElement.setAttribute('data-theme', theme);
    else document.documentElement.removeAttribute('data-theme');
    $('#theme-toggle').textContent = theme === 'light' ? '☀' : theme === 'dark' ? '☾' : '◐';
    $('#theme-toggle').title = 'Theme: ' + (theme || 'auto');
  }
  $('#theme-toggle').addEventListener('click', () => {
    const order = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(store.get('theme', 'auto')) + 1) % order.length];
    store.set('theme', next);
    applyTheme(next);
  });
  applyTheme(store.get('theme', 'auto'));
  $('#help-toggle').addEventListener('click', () => $('#help-dialog').showModal());

  // ---------------------------------------------------------------- router

  function parseRoute() {
    let raw = location.hash.replace(/^#\/?/, '');
    if (!raw.includes('?')) raw = raw.replace(/%3F/i, '?'); // some launchers percent-encode the fragment's "?"
    const [path, query] = raw.split('?');
    const params = new URLSearchParams(query || '');
    if (params.get('tab') && TABS.some(([k]) => k === params.get('tab'))) state.tab = params.get('tab');
    if (['replay', 'production', 'diff'].includes(params.get('tr'))) state.trMode = params.get('tr');
    const parts = path.split('/').filter(Boolean).map((p) => { try { return decodeURIComponent(p); } catch (e) { return p; } });
    if (parts[0] === 'verdicts') return { view: 'verdicts' };
    if (parts[0] === 'run' && parts[1]) {
      if ((parts[2] === 'c' || parts[2] === 'p') && parts[3]) return { view: 'conv', runId: parts[1], kind: parts[2] === 'p' ? 'production' : 'replay', id: parts[3] };
      return { view: 'day', runId: parts[1] };
    }
    return { view: 'home' };
  }

  async function render() {
    const token = ++state.renderToken;
    const route = parseRoute();
    const prev = state.route;
    state.route = route;
    state.targets = [];
    const app = $('#app');
    try {
      const runs = await loadRuns();
      if (token !== state.renderToken) return;
      updateRunSelect(runs, route.runId);
      $('#nav-day').classList.toggle('on', route.view === 'day' || route.view === 'conv');
      $('#nav-verdicts').classList.toggle('on', route.view === 'verdicts');
      let view;
      if (route.view === 'home') {
        if (runs.length) { location.replace('#/run/' + encodeURIComponent(runs[0].run_id)); return; }
        view = emptyStore();
      } else if (route.view === 'day') view = await dayPage(route, token);
      else if (route.view === 'conv') view = await convPage(route, token);
      else view = await verdictsPage(token);
      if (token !== state.renderToken || !view) return;
      app.replaceChildren(view);
      if (route.view === 'day') {
        restoreSelection(route.runId, prev);
      } else {
        window.scrollTo(0, 0);
      }
      if (route.view === 'conv') focusTarget(0, false);
    } catch (err) {
      if (token !== state.renderToken) return;
      app.replaceChildren(h('p', { class: 'empty error' }, 'Could not load: ' + err.message));
    }
  }

  function updateRunSelect(runs, current) {
    const sel = $('#run-select');
    const runId = current || (state.lastRun && runs.some((r) => r.run_id === state.lastRun) ? state.lastRun : runs[0] && runs[0].run_id);
    if (current) state.lastRun = current;
    sel.replaceChildren(...runs.map((r) => h('option', { value: r.run_id, selected: r.run_id === runId }, (r.date || r.day_id) + ' · ' + shortRef(r) + ' · ' + r.run_id)));
    $('#nav-day').setAttribute('href', runId ? '#/run/' + encodeURIComponent(runId) : '#/');
  }
  $('#run-select').addEventListener('change', (e) => { location.hash = '#/run/' + encodeURIComponent(e.target.value); });

  function shortRef(run) {
    const ref = run.ref || '';
    if (/^[0-9a-f]{40}$/i.test(ref)) return ref.slice(0, 8);
    return ref + (run.commit ? '@' + String(run.commit).slice(0, 7) : '');
  }

  function emptyStore() {
    return h('div', { class: 'empty' },
      h('p', null, 'No runs in this store yet.'),
      h('p', null, 'Write a synthetic sample with ', h('code', null, 'python -m testing.pipeline_lab.inspector.sample_run --root <dir>'), ' and serve that root.'));
  }

  // ---------------------------------------------------------------- day page

  const STATUS_CLASS = { same: 'st-same', changed: 'st-changed', new: 'st-new', missing: 'st-missing', 'discard flipped': 'st-flipped' };
  function statusChip(status, withVs) {
    return h('span', { class: 'chip ' + (STATUS_CLASS[status] || '') }, status, withVs && status !== 'same' && status !== 'new' ? h('span', { class: 'vsprod' }, ' vs production') : null);
  }

  async function dayPage(route, token) {
    const ov = await loadOverview(route.runId, true);
    if (token !== state.renderToken) return null;
    TZ = ov.day.timezone || 'UTC';
    const panel = h('aside', { class: 'day-panel' }, h('div', { class: 'card' }, h('p', { class: 'empty' }, 'Loading day panel…')));
    const page = h('div', { class: 'page day' }, dayHeader(ov), timeline(ov, route.runId), h('div', { class: 'day-grid' }, conversationList(ov, route.runId), panel));
    loadDayPanel(route.runId, panel);
    return page;
  }

  function flatten(obj, prefix, out) {
    out = out || [];
    for (const [k, v] of Object.entries(obj || {})) {
      const key = prefix ? prefix + '.' + k : k;
      if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out);
      else out.push([key, Array.isArray(v) ? v.join(', ') : String(v)]);
    }
    return out;
  }

  function dayHeader(ov) {
    const run = ov.run;
    const cov = ov.day.coverage || {};
    const overlay = flatten(run.overlay);
    const spendPct = run.budget_usd ? Math.min(100, (100 * (run.spend_usd || 0)) / run.budget_usd) : 0;
    const items = [
      h('span', { class: 'item', title: 'ref under test' + (run.commit ? ' · ' + run.commit : '') }, h('span', { class: 'label' }, 'ref'), h('code', null, run.ref || '—'), run.commit ? h('code', { class: 'muted' }, String(run.commit).slice(0, 7)) : null),
      h('details', { class: 'inline item' },
        h('summary', null, h('span', { class: 'label' }, 'overlay'), ' ', overlay.length ? overlay.length + ' setting' + (overlay.length === 1 ? '' : 's') + ' ▾' : 'none'),
        overlay.length ? h('div', { class: 'pop' }, h('table', null, overlay.map(([k, v]) => h('tr', null, h('td', null, k), h('td', null, v))))) : null),
      run.stt ? h('span', { class: 'item', title: 'where the transcripts came from' }, h('span', { class: 'label' }, 'stt'), h('code', null, run.stt)) : null,
      run.engine === 'fake' ? h('span', { class: 'chip badge-warn', title: 'Plumbing check: a stand-in replaced the product pipeline' }, 'engine: fake') : null,
      run.pipeline === 'v3' ? h('span', { class: 'chip', title: 'Conversations v3: the day\'s recordings were fed to the real v3 builder, which planned these conversations. Production is its v3 result for the day.' }, 'pipeline: v3') : null,
      h('span', { class: 'item spend', title: 'spend vs cap' }, h('span', { class: 'label' }, 'spend'), h('span', { class: 'num' }, usd(run.spend_usd) + ' / ' + usd(run.budget_usd)), h('span', { class: 'meter' + (spendPct > 80 ? ' hot' : '') }, h('i', { style: 'width:' + spendPct.toFixed(1) + '%' }))),
      h('span', { class: 'item' }, h('span', { class: 'label' }, 'wall'), h('span', { class: 'num' }, dur(run.wall_seconds))),
      run.status && run.status !== 'complete' ? h('span', { class: 'chip badge-warn' }, run.status) : null,
      run.start_state === 'approximate' ? h('span', { class: 'chip badge-warn', title: 'Start state comes from a snapshot taken after the day began' }, 'start state: approximate') : null,
      h('span', { class: 'chip', title: (cov.audio_seconds ? dur(cov.audio_seconds) + ' of audio. ' : '') + 'Grey bands on the timeline are gaps with unknown audio.' },
        'audio ' + (cov.with_audio !== undefined ? cov.with_audio + '/' + (cov.conversations || 0) : '?') + (cov.gaps && cov.gaps.length ? ' · ' + cov.gaps.length + ' gap' + (cov.gaps.length === 1 ? '' : 's') : '')),
      (run.warnings || []).length ? h('details', { class: 'inline item' }, h('summary', null, (run.warnings.length) + ' warning' + (run.warnings.length === 1 ? '' : 's') + ' ▾'), h('div', { class: 'pop' }, h('ul', null, run.warnings.map((w) => h('li', null, w))))) : null,
    ];
    return h('div', { class: 'day-head' },
      h('h1', null, longDate(ov.day.date), h('span', { class: 'tz' }, ov.day.timezone || 'UTC')),
      h('div', { class: 'meta' }, items));
  }

  function windowOf(ov) {
    const w = ov.day.window;
    let start = w ? ms(w.start) : NaN, end = w ? ms(w.end) : NaN;
    if (isNaN(start)) {
      const all = ov.timeline.replay.concat(ov.timeline.production).map((c) => ms(c.started_at)).filter((x) => !isNaN(x));
      start = all.length ? Math.min(...all) : Date.now();
      end = start + 86400000;
    }
    if (state.fit === 'active') {
      const rows = ov.timeline.replay.concat(ov.timeline.production);
      const s = rows.map((c) => ms(c.started_at)).filter((x) => !isNaN(x));
      const e = rows.map((c) => ms(c.finished_at)).filter((x) => !isNaN(x));
      if (s.length) {
        const hour = 3600000;
        const a = Math.max(start, Math.floor((Math.min(...s) - start) / hour) * hour + start);
        const b = Math.min(end, Math.ceil((Math.max(...e) - start) / hour) * hour + start);
        if (b > a) return { start: a, end: b, full: [start, end] };
      }
    }
    return { start, end, full: [start, end] };
  }

  function timeline(ov, runId) {
    const win = windowOf(ov);
    const span = win.end - win.start;
    const pct = (t) => ((t - win.start) / span) * 100;
    const place = (s, e) => {
      const a = Math.max(win.start, ms(s)), b = Math.min(win.end, isNaN(ms(e)) ? ms(s) : ms(e));
      if (isNaN(a) || b < win.start || a > win.end) return null;
      return 'left:' + pct(a).toFixed(3) + '%;width:' + Math.max(0, pct(b) - pct(a)).toFixed(3) + '%';
    };
    const hours = [];
    for (let t = win.start; t <= win.end + 1; t += 3600000) hours.push(t);
    const axis = h('div', { class: 'tl-axis' }, hours.map((t, i) => {
      const major = (Math.round((t - win.full[0]) / 3600000)) % 3 === 0;
      return h('span', { class: major ? '' : 'minor', style: 'left:' + pct(t).toFixed(3) + '%' }, i === hours.length - 1 && t >= win.end ? '' : clock(new Date(t).toISOString()));
    }));
    const gaps = (ov.timeline.gaps || []).map((g) => { const st = place(g.start, g.end); return st ? h('div', { class: 'tl-gap', style: st, title: 'Gap: ' + (g.kind || 'unknown') + ' audio, ' + clock(g.start) + '–' + clock(g.end) }) : null; });
    const grid = () => hours.slice(1, -1).map((t) => h('div', { class: 'tl-hour', style: 'left:' + pct(t).toFixed(3) + '%' }));
    const blocks = (rows, prod) => rows.map((c) => {
      const st = place(c.started_at, c.finished_at);
      if (!st) return null;
      const status = prod ? (c.status === 'missing' ? 'missing' : '') : c.status;
      const cls = ['tl-block', prod ? 'prod' : 'r', c.discarded ? 'discarded' : '', c.hidden ? 'offhome' : '', status ? STATUS_CLASS[status] : ''].join(' ');
      const twinIds = prod ? [c.id] : (c.baseline || []).map((b) => b && b.id);
      const href = prod ? (c.status === 'missing' ? convHref(runId, { kind: 'production', id: c.id }) : null) : convHref(runId, c);
      const title = clock(c.started_at) + '–' + clock(c.finished_at) + '  ' + (c.title || (c.discarded ? '(discarded)' : '(untitled)')) + (status ? '  · ' + status : '') + (c.hidden ? '  · not on Home' + (c.hidden_reason ? ' (' + c.hidden_reason.replace(/_/g, ' ') + ')' : '') : '');
      return h('button', {
        class: cls, style: st, title, type: 'button',
        dataset: { twins: twinIds.filter(Boolean).join(' '), id: c.id, side: prod ? 'p' : 'r' },
        onclick: () => {
          if (href) location.hash = href;
          else {
            const owner = ov.conversations.find((r) => r.kind === 'replay' && (r.baseline || []).some((b) => b && b.id === c.id));
            if (owner) location.hash = convHref(runId, owner);
          }
        },
        onmouseenter: (e) => highlightTwins(e.currentTarget, true),
        onmouseleave: (e) => highlightTwins(e.currentTarget, false),
      });
    });
    const fitToggle = h('span', { class: 'seg-toggle', role: 'group', 'aria-label': 'Timeline range' },
      ['day', 'active'].map((f) => h('button', { type: 'button', class: state.fit === f ? 'on' : '', onclick: () => { state.fit = f; store.set('fit', f); render(); } }, f === 'day' ? '24 h' : 'Active hours')));
    return h('section', { class: 'card timeline', 'aria-label': 'Timeline' },
      h('div', { class: 'tl-head' }, h('span', { class: 'label' }, 'Timeline'), fitToggle),
      h('div', { class: 'tl-grid' },
        h('span'), axis,
        h('span', { class: 'tl-rowlabel' }, 'Replay'), h('div', { class: 'tl-track' }, gaps, grid(), blocks(ov.timeline.replay, false)),
        h('span', { class: 'tl-rowlabel' }, 'Production'), h('div', { class: 'tl-track' }, gaps.map((g) => g && g.cloneNode()), grid(), blocks(ov.timeline.production, true))),
      h('div', { class: 'tl-legend' },
        h('span', null, h('i', { style: 'background:var(--block-replay)' }), 'kept'),
        h('span', null, h('i', { style: 'background:repeating-linear-gradient(135deg,var(--block-prod) 0 2px,transparent 2px 5px);box-shadow:inset 0 0 0 1px var(--block-prod)' }), 'discarded'),
        h('span', null, h('i', { style: 'background:var(--changed)' }), 'changed'),
        h('span', null, h('i', { style: 'background:var(--new)' }), 'new'),
        h('span', null, h('i', { style: 'background:var(--flipped)' }), 'discard flipped'),
        h('span', null, h('i', { style: 'background:var(--missing)' }), 'missing in replay'),
        h('span', null, h('i', { style: 'background:var(--gap)' }), 'no audio / unknown'),
        ov.run.pipeline === 'v3' ? h('span', null, h('i', { class: 'offhome-key' }), 'not on Home (v3)') : null));
  }

  function highlightTwins(el, on) {
    const ids = (el.dataset.twins || '').split(' ').filter(Boolean);
    if (el.dataset.side === 'r') {
      $$('.tl-block.prod').forEach((b) => b.classList.toggle('hl', on && ids.includes(b.dataset.id)));
    } else {
      $$('.tl-block.r').forEach((b) => b.classList.toggle('hl', on && (b.dataset.twins || '').split(' ').includes(el.dataset.id)));
    }
  }

  const FILTERS = [
    ['changed', 'Changed', (r) => r.status !== 'same'],
    ['discarded', 'Discarded', (r) => r.discarded],
    ['verdict', 'Has verdict', (r) => (r.verdicts.good || 0) + (r.verdicts.bad || 0) > 0],
    ['pushes', 'Has pushes', (r) => r.counts.pushes > 0],
  ];

  const HOME_FILTER = ['home', 'On Home', (r) => r.hidden === false];
  function filtersFor(ov) { return ov.run.pipeline === 'v3' ? [HOME_FILTER].concat(FILTERS) : FILTERS; }

  function visibleRows(ov) {
    const q = state.search.trim().toLowerCase();
    return ov.conversations.filter((r) => {
      for (const [key, , test] of filtersFor(ov)) if (state.filters[key] && !test(r)) return false;
      if (q && !((r.title || '') + ' ' + (r.baseline || []).map((b) => b && b.title).join(' ') + ' ' + r.status).toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function conversationList(ov, runId) {
    const listEl = h('ul', { class: 'convlist card', role: 'listbox', 'aria-label': 'Conversations' });
    const statEl = h('p', { class: 'statline' });
    const filterBtns = filtersFor(ov).map(([key, label, test]) => h('button', {
      type: 'button', class: 'filter' + (state.filters[key] ? ' on' : ''), 'aria-pressed': String(!!state.filters[key]),
      onclick: (e) => { state.filters[key] = !state.filters[key]; store.set('filters', state.filters); e.currentTarget.classList.toggle('on', state.filters[key]); e.currentTarget.setAttribute('aria-pressed', String(state.filters[key])); fill(); },
    }, label, h('span', { class: 'n' }, ov.conversations.filter(test).length)));
    const search = h('input', { class: 'search', id: 'conv-search', type: 'search', placeholder: 'Filter by title or status  ( / )', value: state.search, 'aria-label': 'Filter conversations',
      oninput: (e) => { state.search = e.target.value; fill(); },
      onkeydown: (e) => { if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); e.target.blur(); } } });

    function fill() {
      const rows = visibleRows(ov);
      const st = ov.statuses || {};
      const replayed = ov.conversations.filter((r) => r.kind === 'replay').length;
      statEl.replaceChildren();
      append(statEl, [
        h('b', null, replayed), ' replayed', ' · ', h('b', null, st.changed || 0), ' changed', ' · ', h('b', null, st.new || 0), ' new', ' · ',
        h('b', null, st.missing || 0), ' missing', ' · ', h('b', null, st['discard flipped'] || 0), ' discard flipped', ' · ', h('b', null, st.same || 0), ' same',
        rows.length !== ov.conversations.length ? h('span', null, '  — showing ' + rows.length) : null]);
      listEl.replaceChildren(...(rows.length ? rows.map((r) => convRow(r, runId)) : [h('li', { class: 'empty' }, 'No conversations match.')]));
      const sel = state.selected.get(runId);
      if (sel) markSelected(sel, false);
    }
    fill();
    return h('section', { 'aria-label': 'Conversations' }, h('div', { class: 'toolbar' }, search, filterBtns), statEl, listEl);
  }

  function convRow(r, runId) {
    const b = (r.baseline || [])[0];
    const title = r.title || (b && b.title) || '';
    const marks = [];
    for (let i = 0; i < (r.verdicts.good || 0); i++) marks.push(h('i', { class: 'good' }));
    for (let i = 0; i < (r.verdicts.bad || 0); i++) marks.push(h('i', { class: 'bad' }));
    return h('li', { role: 'option' }, h('a', {
      class: 'crow' + (r.discarded ? ' discarded' : '') + (r.hidden ? ' offhome' : '') + (r.kind === 'production' ? ' missing' : ''),
      href: convHref(runId, r), dataset: { key: convKey(r) },
      onclick: () => { state.selected.set(runId, convKey(r)); },
    },
    h('time', { class: 'ts' }, clock(r.started_at)),
    h('span', { class: 'dur' }, dur(r.duration)),
    h('span', { class: 'title' }, r.emoji ? h('span', { class: 'emoji', 'aria-hidden': 'true' }, r.emoji) : null,
      h('span', { class: 't' }, title || (r.discarded ? 'Discarded' : 'Untitled')),
      r.discarded ? h('span', { class: 'why' }, [title ? 'discarded' : '', r.discard_reason ? r.discard_reason.replace(/_/g, ' ') : ''].filter(Boolean).join(' · ')) : null,
      r.status === 'changed' && r.reasons.length ? h('span', { class: 'why' }, r.reasons.join(' · ')) : null,
      r.hidden ? h('span', { class: 'why', title: 'v3 kept it off the phone\'s Home list' }, 'not on Home' + (r.hidden_reason ? ' · ' + r.hidden_reason.replace(/_/g, ' ') : '')) : null),
    h('span', { class: 'counts' },
      r.counts.tasks ? h('span', { class: 'chip count', title: 'tasks' }, r.counts.tasks + ' task' + (r.counts.tasks === 1 ? '' : 's')) : null,
      r.counts.memories ? h('span', { class: 'chip count', title: 'memories' }, r.counts.memories + ' mem') : null,
      r.counts.pushes ? h('span', { class: 'chip count', title: 'would-have-fired pushes' }, r.counts.pushes + ' push' + (r.counts.pushes === 1 ? '' : 'es')) : null,
      r.recordings > 1 ? h('span', { class: 'chip count', title: 'recordings this v3 conversation was planned over' }, r.recordings + ' rec') : null),
    h('span', { class: 'stat' }, marks.length ? h('span', { class: 'vdots', title: 'verdicts' }, marks) : null, statusChip(r.status))));
  }

  function markSelected(key, scroll) {
    $$('.crow.sel').forEach((el) => el.classList.remove('sel'));
    $$('.tl-block.sel').forEach((el) => el.classList.remove('sel'));
    const el = $('.crow[data-key="' + CSS.escape(key) + '"]');
    if (el) {
      el.classList.add('sel');
      if (scroll) el.scrollIntoView({ block: 'nearest' });
    }
    const id = key.slice(2);
    const blk = $('.tl-block[data-side="' + (key[0] === 'p' ? 'p' : 'r') + '"][data-id="' + CSS.escape(id) + '"]');
    if (blk) blk.classList.add('sel');
  }

  function restoreSelection(runId, prev) {
    const ov = state.overview.get(runId);
    if (!ov) return;
    let key = state.selected.get(runId);
    if (prev && prev.view === 'conv' && prev.runId === runId) key = (prev.kind === 'production' ? 'p:' : 'c:') + prev.id;
    if (!key) return;
    state.selected.set(runId, key);
    markSelected(key, true);
  }

  function moveSelection(delta) {
    const route = state.route;
    const ov = state.overview.get(route.runId);
    if (!ov) return;
    const rows = visibleRows(ov);
    if (!rows.length) return;
    const cur = state.selected.get(route.runId);
    let idx = rows.findIndex((r) => convKey(r) === cur);
    idx = idx < 0 ? (delta > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, idx + delta));
    state.selected.set(route.runId, convKey(rows[idx]));
    markSelected(convKey(rows[idx]), true);
  }

  async function loadDayPanel(runId, panel) {
    try {
      if (!state.dayPanel.has(runId)) state.dayPanel.set(runId, await getJSON('/api/runs/' + encodeURIComponent(runId) + '/day'));
      const d = state.dayPanel.get(runId);
      panel.replaceChildren(dailySummaryCard(d, runId), goalsCard(d.goals), memoryDeltaCard(d.memory_delta), pushLogCard(d.notifications));
    } catch (err) {
      panel.replaceChildren(h('div', { class: 'card' }, h('p', { class: 'error' }, 'Day panel: ' + err.message)));
    }
  }

  function summarySide(label, value, other, side) {
    if (!value) return h('div', { class: 'side none' }, h('span', { class: 'label' }, label), 'none');
    const o = other || { title: '', overview: '', highlights: [] };
    const hasOther = !!other;
    return h('div', { class: 'side ' + side },
      h('span', { class: 'label' }, label),
      value.title ? h('div', { class: 't' }, hasOther ? diffSide(side === 'new' ? o.title : value.title, side === 'new' ? value.title : o.title, side) : value.title) : null,
      value.overview ? h('p', null, hasOther ? diffSide(side === 'new' ? o.overview : value.overview, side === 'new' ? value.overview : o.overview, side) : value.overview) : null,
      value.highlights && value.highlights.length ? h('ul', null, value.highlights.map((x) => h('li', { class: hasOther && !(o.highlights || []).includes(x) ? (side === 'new' ? 'hl-new' : 'hl-old') : '' }, hasOther && !(o.highlights || []).includes(x) ? h(side === 'new' ? 'ins' : 'del', null, x) : x))) : null);
  }

  function dailySummaryCard(d, runId) {
    const ds = d.daily_summary || {};
    const target = ds.key ? { kind: 'daily_summary', key: ds.key, conversation_id: null, label: 'Daily summary', runId } : null;
    const v = target ? verdictFor(target, ds.verdicts || []) : null;
    return h('section', { class: 'card' },
      h('div', { class: 'section-title' }, 'Daily summary', h('span', { class: 'spacer' }), target ? verdictControls(target, v) : null),
      h('div', { class: 'pair-cols stacked' }, summarySide('Replay', ds.replay, ds.baseline, 'new'), summarySide('Production', ds.baseline, ds.replay, 'old')),
      v && v.note ? h('div', { class: 'item' }, h('div', { class: 'note-line' }, v.note)) : null);
  }

  function goalsCard(goals) {
    const num = (x) => (typeof x === 'number' ? (x <= 1 && x > 0 && !Number.isInteger(x) ? Math.round(x * 100) + '%' : String(x)) : '—');
    return h('section', { class: 'card' }, h('div', { class: 'section-title' }, 'Goals', h('span', { class: 'label' }, goals.length || '')),
      goals.length ? goals.map((g) => {
        const target = typeof g.target === 'number' && g.target > 0 ? g.target : 1;
        const before = typeof g.progress_before === 'number' ? Math.min(100, (100 * g.progress_before) / target) : 0;
        const after = typeof g.progress_after === 'number' ? Math.min(100, (100 * g.progress_after) / target) : before;
        return h('div', { class: 'goal' },
          h('span', null, g.title || g.name || JSON.stringify(g)),
          h('span', { class: 'num' }, num(g.progress_before) + ' → ' + num(g.progress_after) + (typeof g.target === 'number' && g.target !== 1 ? ' / ' + g.target : '')),
          h('div', { class: 'bar' }, h('i', { class: 'after', style: 'width:' + after + '%' }), h('i', { class: 'before', style: 'width:' + before + '%' })),
          g.note ? h('span', { class: 'note' }, g.note) : null);
      }) : h('p', { class: 'pane-note' }, 'No goal changes.'));
  }

  function memText(m) { return typeof m === 'string' ? m : (m && (m.content || m.text)) || JSON.stringify(m); }

  function memoryDeltaCard(delta) {
    delta = delta || {};
    const added = delta.added || [], updated = delta.updated || [], removed = delta.removed || [];
    return h('section', { class: 'card' },
      h('div', { class: 'section-title' }, 'Memory delta', h('span', { class: 'label' }, '+' + added.length + ' ~' + updated.length + ' −' + removed.length)),
      added.length + updated.length + removed.length === 0 ? h('p', { class: 'pane-note' }, 'No memory changes.') : h('ul', { class: 'delta' },
        added.map((m) => h('li', { class: 'add' }, h('span', { class: 'sym' }, '+'), h('span', { class: 'txt' }, memText(m)))),
        updated.map((u) => h('li', { class: 'upd' }, h('span', { class: 'sym' }, '~'), h('span', { class: 'txt' }, u && u.before && u.after ? diffInline(memText(u.before), memText(u.after)) : memText(u)))),
        removed.map((m) => h('li', { class: 'rem' }, h('span', { class: 'sym' }, '−'), h('span', { class: 'txt' }, memText(m))))));
  }

  function diffInline(oldText, newText) {
    const ops = diffTokens(tokens(oldText), tokens(newText));
    return ops.map((op) => (op.t === 'eq' ? op.s : h(op.t === 'ins' ? 'ins' : 'del', null, op.s)));
  }

  function pushLogCard(log) {
    return h('section', { class: 'card' },
      h('div', { class: 'section-title' }, 'Would-have-fired pushes', h('span', { class: 'label' }, (log || []).filter((p) => p.replay).length + ' replay · ' + (log || []).filter((p) => p.baseline).length + ' production')),
      (log || []).length ? h('ul', { class: 'pushlog' }, log.map((p) => {
        const n = p.replay || p.baseline;
        const state_ = p.state === 'added' ? 'only in replay' : p.state === 'removed' ? 'only in production' : p.state;
        return h('li', null, h('time', { class: 'when' }, clock(n.at)),
          h('div', null,
            h('div', { class: 'pt' }, p.state === 'changed' ? diffSide(p.baseline.title, p.replay.title, 'new') : n.title),
            h('div', { class: 'pb' }, p.state === 'changed' ? diffSide(p.baseline.body, p.replay.body, 'new') : n.body),
            h('div', { class: 'meta' }, h('span', { class: 'chip ' + (p.state === 'same' ? 'st-same' : p.state === 'changed' ? 'st-changed' : p.state === 'added' ? 'st-added' : 'st-removed') }, state_), n.trigger ? h('span', null, n.trigger.replace(/_/g, ' ')) : null)));
      })) : h('p', { class: 'pane-note' }, 'No pushes would have fired.'));
  }

  // ---------------------------------------------------------------- verdicts (shared)

  const ICONS = {
    up: 'M7 10v10H4V10h3zm2 10h8.2a2 2 0 0 0 2-1.6l1.3-6A2 2 0 0 0 18.5 10H14l.7-3.6a1.6 1.6 0 0 0-2.9-1.2L9 10v10z',
    down: 'M7 14V4H4v10h3zm2-10h8.2a2 2 0 0 1 2 1.6l1.3 6A2 2 0 0 1 18.5 14H14l.7 3.6a1.6 1.6 0 0 1-2.9 1.2L9 14V4z',
    note: 'M4 17.3V20h2.7l8-8-2.7-2.7-8 8zM17.7 9a.7.7 0 0 0 0-1l-1.7-1.7a.7.7 0 0 0-1 0L13.7 7.6l2.7 2.7L17.7 9z',
  };
  function icon(name) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', ICONS[name]);
    path.setAttribute('fill', 'currentColor');
    svg.append(path);
    return svg;
  }

  function targetId(t) { return [t.kind, t.key, t.conversation_id || ''].join('|'); }
  function verdictFor(target, rows) {
    let best = null;
    for (const v of rows || []) {
      // Marks are stored under the production id when one exists (RULINGS 4); match either id.
      const ids = [target.conversation_id || null, ...(target.aliases || [])];
      if (v.item_kind === target.kind && v.item_key === target.key && (ids.includes(v.conversation_id || null) || (v.replay_conversation_id && v.replay_conversation_id === target.conversation_id))) {
        if (!best || (v.at || '') >= (best.at || '')) best = v;
      }
    }
    return best;
  }

  function verdictControls(target, current) {
    const wrap = h('span', { class: 'vd', dataset: { target: targetId(target) } });
    target.current = current;
    fillControls(wrap, target);
    return wrap;
  }
  function fillControls(wrap, target) {
    const cur = target.current;
    wrap.replaceChildren(
      h('button', { type: 'button', class: 'good' + (cur && cur.mark === 'good' ? ' on' : ''), title: 'Good (1)', 'aria-label': 'Mark good', 'aria-pressed': String(!!(cur && cur.mark === 'good')), onclick: (e) => { e.preventDefault(); e.stopPropagation(); submitVerdict(target, 'good', cur ? cur.note : ''); } }, icon('up')),
      h('button', { type: 'button', class: 'bad' + (cur && cur.mark === 'bad' ? ' on' : ''), title: 'Bad (2)', 'aria-label': 'Mark bad', 'aria-pressed': String(!!(cur && cur.mark === 'bad')), onclick: (e) => { e.preventDefault(); e.stopPropagation(); submitVerdict(target, 'bad', cur ? cur.note : ''); } }, icon('down')),
      h('button', { type: 'button', class: 'note' + (cur && cur.note ? ' on' : ''), title: cur && cur.note ? 'Note: ' + cur.note : 'Add a note (n)', 'aria-label': 'Note', onclick: (e) => { e.preventDefault(); e.stopPropagation(); openNote(target); } }, icon('note')));
  }

  async function submitVerdict(target, mark, note) {
    try {
      const body = await postJSON('/api/verdicts', { run_id: target.runId, conversation_id: target.conversation_id, item_kind: target.kind, item_key: target.key, mark, note: note || '' });
      const row = body.verdict;
      target.current = row;
      for (const wrap of $$('.vd[data-target="' + CSS.escape(targetId(target)) + '"]')) fillControls(wrap, target);
      const holder = target.el;
      if (holder) {
        let line = $('.note-line', holder);
        if (row.note) { if (!line) { line = h('div', { class: 'note-line' }); holder.append(line); } line.textContent = row.note; } else if (line) line.remove();
      }
      // keep caches in step without refetching everything
      for (const p of state.detail.values()) p.then((d) => { if (d.run_id === target.runId) d.verdicts.push(row); }).catch(() => {});
      state.overview.delete(target.runId);
      if (target.kind === 'daily_summary') state.dayPanel.delete(target.runId);
      toast((mark === 'good' ? '👍 ' : '👎 ') + target.label + (row.note ? ' · note saved' : ''));
    } catch (err) {
      toast('Verdict not saved: ' + err.message, true);
    }
  }

  function openNote(target) {
    const dlg = $('#note-dialog');
    const cur = target.current;
    $('#note-target').textContent = target.label + (target.preview ? ' — ' + target.preview : '');
    $('#note-text').value = cur ? cur.note || '' : '';
    for (const r of $$('input[name="mark"]', dlg)) r.checked = cur ? r.value === cur.mark : r.value === 'bad';
    dlg.returnValue = '';
    dlg.onclose = () => {
      if (dlg.returnValue !== 'save') return;
      const mark = ($('input[name="mark"]:checked', dlg) || {}).value || 'bad';
      submitVerdict(target, mark, $('#note-text').value.trim());
    };
    dlg.showModal();
    $('#note-text').focus();
  }
  $('#note-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('#note-dialog').close('save'); }
  });

  /* Register an element as a keyboard-focusable verdict target on the current page. */
  function vt(el, target, group) {
    el.classList.add('vt');
    target.el = el;
    el.addEventListener('click', (e) => {
      if (e.target.closest('a, summary, audio, .seg-toggle')) return;
      const idx = activeTargets().findIndex((t) => t.target === target);
      if (idx >= 0) focusTarget(idx, false);
      else pinTarget(target);
    });
    state.targets.push({ el, target, group });
    return el;
  }
  function activeTargets() { return state.targets.filter((t) => t.group === state.tab && document.contains(t.el)); }
  /* A target outside the open tab (transcript, speakers, boundary) is focused by clicking it. */
  function pinTarget(target) {
    $$('.vt.focus').forEach((el) => el.classList.remove('focus'));
    state.pinned = target;
    if (target.el) target.el.classList.add('focus');
  }
  function focusTarget(idx, scroll) {
    const list = activeTargets();
    state.pinned = null;
    $$('.vt.focus').forEach((el) => el.classList.remove('focus'));
    if (!list.length) return;
    state.focus = Math.max(0, Math.min(list.length - 1, idx));
    const el = list[state.focus].el;
    el.classList.add('focus');
    if (scroll !== false) el.scrollIntoView({ block: 'nearest' });
  }
  function focusedTarget() { if (state.pinned && document.contains(state.pinned.el)) return state.pinned; const list = activeTargets(); return list.length ? list[Math.min(state.focus, list.length - 1)].target : null; }

  // ---------------------------------------------------------------- conversation page

  const TABS = [['summary', 'Summary'], ['tasks', 'Tasks'], ['memories', 'Memories'], ['pushes', 'Pushes'], ['calls', 'Calls']];

  async function convPage(route, token) {
    const ovP = loadOverview(route.runId);
    let detail;
    try {
      detail = await loadDetail(route.runId, route.kind, route.id);
    } catch (err) {
      if (err.status === 404 && route.kind === 'replay') { location.replace('#/run/' + encodeURIComponent(route.runId) + '/p/' + encodeURIComponent(route.id)); return null; }
      throw err;
    }
    const ov = await ovP;
    if (token !== state.renderToken) return null;
    TZ = ov.day.timezone || 'UTC';
    state.selected.set(route.runId, (route.kind === 'production' ? 'p:' : 'c:') + route.id);
    let rows = visibleRows(ov);
    let idx = rows.findIndex((r) => convKey(r) === state.selected.get(route.runId));
    if (idx < 0) { rows = ov.conversations; idx = rows.findIndex((r) => convKey(r) === state.selected.get(route.runId)); }
    const prev = idx > 0 ? rows[idx - 1] : null, next = idx >= 0 && idx < rows.length - 1 ? rows[idx + 1] : null;
    state.nav = { prev, next };
    for (const n of [next, prev]) if (n) loadDetail(route.runId, n.kind, n.id).catch(() => {});

    const conv = detail.replay || detail.baseline;
    const cid = route.id;
    const s = conv.structured || {};
    const notices = [];
    if (conv.evaluable && conv.evaluable.boundaries === false) notices.push(h('div', { class: 'notice' }, 'Boundaries unevaluable here' + (conv.evaluable.reason ? ': ' + conv.evaluable.reason : '') + '.'));
    if (detail.kind === 'production') notices.push(h('div', { class: 'notice info' }, 'Production had this conversation; the replay did not produce it. Everything below is production only.'));
    if ((detail.baselines || []).length > 1) notices.push(h('div', { class: 'notice info' }, 'The replay merged ' + detail.baselines.length + ' production conversations: ' + detail.baselines.map((b) => clock(b.started_at) + ' ' + (b.title || 'untitled')).join(' · ') + '.'));
    const siblings = detail.replay && detail.baseline ? ov.conversations.filter((r) => r.kind === 'replay' && r.id !== cid && (r.baseline || []).some((b) => b && b.id === detail.baseline.id)) : [];
    if (siblings.length) notices.push(h('div', { class: 'notice info' }, 'The replay split this production conversation; also see ', siblings.map((r, i) => [i ? ', ' : '', h('a', { href: convHref(route.runId, r) }, clock(r.started_at) + ' ' + (r.title || 'untitled'))]), '.'));
    if (detail.baseline && detail.replay) {
      const ds = (ms(detail.replay.started_at) - ms(detail.baseline.started_at)) / 1000, de = (ms(detail.replay.finished_at) - ms(detail.baseline.finished_at)) / 1000;
      if (Math.abs(ds) > 30 || Math.abs(de) > 30) notices.push(h('div', { class: 'notice info' }, 'Boundary vs production: start ' + signed(ds) + ', end ' + signed(de) + ' (production ' + clock(detail.baseline.started_at) + '–' + clock(detail.baseline.finished_at) + ').'));
    }

    const header = h('div', { class: 'conv-head' },
      h('a', { class: 'back', href: '#/run/' + encodeURIComponent(route.runId) }, '← ', longDate(ov.day.date)),
      h('span'),
      h('div', { class: 'conv-nav' },
        h('a', { class: 'btn', href: prev ? convHref(route.runId, prev) : null, 'aria-disabled': prev ? null : 'true', title: 'Previous (k)' }, '↑ k'),
        h('a', { class: 'btn', href: next ? convHref(route.runId, next) : null, 'aria-disabled': next ? null : 'true', title: 'Next (j)' }, '↓ j'),
        idx >= 0 ? h('span', { class: 'num' }, (idx + 1) + '/' + rows.length) : null),
      h('h1', null, s.emoji ? h('span', { 'aria-hidden': 'true' }, s.emoji) : null, s.title ? s.title : h('span', { class: 'untitled' }, conv.discarded ? 'Discarded conversation' : 'Untitled'), statusChip(detail.status, true)),
      h('div', { class: 'meta' },
        h('span', { class: 'item num' }, clock(conv.started_at) + '–' + clock(conv.finished_at) + ' · ' + dur((ms(conv.finished_at) - ms(conv.started_at)) / 1000)),
        conv.lane ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'lane'), conv.lane) : null,
        conv.language ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'lang'), conv.language) : null,
        conv.discarded ? h('span', { class: 'chip' }, 'discarded' + (conv.discard_reason ? ' · ' + conv.discard_reason.replace(/_/g, ' ') : '')) : null,
        detail.replay && detail.baseline && detail.baseline.discarded !== detail.replay.discarded ? h('span', { class: 'chip st-flipped' }, 'production ' + (detail.baseline.discarded ? 'discarded' : 'kept') + ' it') : null,
        detail.reasons && detail.reasons.length ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'differs'), detail.reasons.join(' · ')) : null,
        v3Meta(conv, detail)));

    const ctx = { runId: route.runId, cid, detail };
    return h('div', { class: 'page conv' }, header, notices,
      h('div', { class: 'conv-grid' }, leftColumn(ctx), rightColumn(ctx)));
  }

  function homeText(v) {
    if (!v) return '';
    return v.visible ? 'on Home' : 'not on Home' + (v.home_hidden_reason ? ' · ' + v.home_hidden_reason.replace(/_/g, ' ') : '');
  }

  function v3Meta(conv, detail) {
    const v = conv.v3;
    if (!v) return null;
    const other = detail.replay && detail.baseline && detail.baseline.v3 ? detail.baseline.v3 : null;
    const recs = conv.recordings || [];
    return [
      h('span', { class: 'chip' + (v.visible ? '' : ' offhome'), title: 'What the phone\'s Home list does with this v3 conversation' }, homeText(v)),
      other && other.visible !== v.visible ? h('span', { class: 'chip st-flipped', title: 'vs production' }, 'production: ' + homeText(other)) : null,
      v.kind ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'kind'), v.kind.replace(/_/g, ' '), other && other.kind && other.kind !== v.kind ? h('span', { class: 'vsprod' }, ' (production: ' + other.kind.replace(/_/g, ' ') + ')') : null) : null,
      recs.length ? h('details', { class: 'inline item' }, h('summary', null, h('span', { class: 'label' }, 'recordings'), ' ' + recs.length + ' ▾'), h('div', { class: 'pop' }, h('ul', null, recs.map((x) => h('li', null, h('code', null, x)))))) : null,
      v.process_failed ? h('span', { class: 'chip badge-warn' }, 'notes failed' + (v.process_failure_reason ? ' · ' + v.process_failure_reason : '')) : null,
      v.backfilled ? h('span', { class: 'chip', title: 'Production made this row in a backfill pass, not live' }, 'backfilled') : null,
    ];
  }

  function sectionsView(sections) {
    if (!sections || !sections.length) return null;
    return h('div', { class: 'sections' }, sections.map((x) => h('div', { class: 'section' }, h('div', { class: 'sh' }, x.heading || x.title || ''), x.body_markdown ? h('div', { class: 'sb' }, x.body_markdown) : null)));
  }

  function signed(seconds) { return (seconds >= 0 ? '+' : '−') + dur(Math.abs(seconds)); }

  function makeTarget(ctx, kind, key, label, preview) {
    const r = (ctx.detail && ctx.detail.replay) || {};
    const aliases = (r.baseline_ids && r.baseline_ids.length ? r.baseline_ids : (r.baseline_id ? [r.baseline_id] : []));
    return { kind, key, conversation_id: ctx.cid, aliases, runId: ctx.runId, label, preview };
  }

  function leftColumn(ctx) {
    const d = ctx.detail;
    const audio = d.audio;
    const player = h('div', { class: 'card player' });
    let audioEl = null;
    if (audio) {
      audioEl = h('audio', { controls: true, preload: 'metadata', src: audio.url, id: 'player' });
      audioEl.playbackRate = state.rate;
      let seeded = false;
      audioEl.addEventListener('loadedmetadata', () => { if (!seeded) { seeded = true; audioEl.currentTime = Math.max(0, audio.offset || 0); } audioEl.playbackRate = state.rate; });
      const rateBtns = h('span', { class: 'seg-toggle', role: 'group', 'aria-label': 'Speed' }, [1, 1.5, 2].map((r) => h('button', { type: 'button', class: state.rate === r ? 'on' : '', onclick: (e) => {
        state.rate = r; store.set('rate', r); audioEl.playbackRate = r; $$('button', e.currentTarget.parentNode).forEach((b) => b.classList.toggle('on', b === e.currentTarget));
      } }, r + '×')));
      const follow = h('label', null, h('input', { type: 'checkbox', checked: state.follow, onchange: (e) => { state.follow = e.target.checked; store.set('follow', state.follow); } }), 'Follow');
      player.append(audioEl, h('div', { class: 'row' }, rateBtns, follow, h('span', { class: 'spacer' }), h('span', { title: 'Clip start' }, 'clip ' + clock(audio.start) + '–' + clock(audio.end))));
    } else {
      player.append(h('div', { class: 'row' }, 'No audio for this conversation (unknown or not captured).'));
    }

    const hasBoth = !!(d.replay && d.baseline);
    state.trMode = d.replay ? (hasBoth ? state.trMode : 'replay') : 'production';
    const body = h('div', { class: 'transcript', id: 'transcript' });
    const modes = h('span', { class: 'seg-toggle', role: 'group', 'aria-label': 'Transcript' },
      (d.replay ? (hasBoth ? ['replay', 'production', 'diff'] : ['replay']) : ['production']).map((m) => h('button', {
        type: 'button', class: state.trMode === m ? 'on' : '', dataset: { mode: m },
        onclick: () => setTrMode(m),
      }, m === 'diff' ? 'Diff' : m[0].toUpperCase() + m.slice(1))));
    const keys = (d.replay ? d.keys.replay : d.keys.baseline) || {};
    const vg = h('span', { class: 'vgroup' });
    for (const [kind, label] of [['transcript', 'Transcript'], ['speaker', 'Speakers'], ['boundary', 'Boundary']]) {
      if (!keys[kind]) continue;
      const target = makeTarget(ctx, kind, keys[kind], label);
      const el = h('span', null, label, verdictControls(target, verdictFor(target, d.verdicts)));
      vg.append(vt(el, target, 'transcript-head'));
    }
    const card = h('div', { class: 'card', style: 'margin-top:10px;display:flex;flex-direction:column;min-height:0' },
      h('div', { class: 'tr-head' }, h('span', { class: 'label' }, 'Transcript'), modes, vg), body);

    function setTrMode(m) {
      state.trMode = m;
      $$('button', modes).forEach((b) => b.classList.toggle('on', b.dataset.mode === m));
      fillTranscript();
    }
    ctx.setTrMode = setTrMode;
    ctx.trModes = () => $$('button', modes).map((b) => b.dataset.mode);

    function fillTranscript() {
      const mode = state.trMode;
      if (mode === 'diff') { body.replaceChildren(...transcriptDiff(d)); return; }
      const conv = mode === 'production' ? d.baseline : d.replay;
      body.replaceChildren(...segmentRows(conv, audio, audioEl));
    }
    fillTranscript();

    if (audioEl) {
      let last = null;
      audioEl.addEventListener('timeupdate', () => {
        const t = audioEl.currentTime;
        const segs = $$('.seg[data-t]', body);
        let hit = null;
        for (const el of segs) {
          if (+el.dataset.t <= t + 0.05 && t < +el.dataset.e) hit = el;
        }
        if (hit === last) return;
        if (last) last.classList.remove('playing');
        last = hit;
        if (hit) {
          hit.classList.add('playing');
          if (state.follow && !audioEl.paused) hit.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
      });
    }
    return h('div', { class: 'left-col' }, player, card);
  }

  function speakerPalette(conv) {
    const map = new Map();
    for (const seg of (conv && conv.segments) || []) {
      const id = seg.is_user ? '__user' : seg.speaker || seg.speaker_name || '?';
      if (!map.has(id)) map.set(id, seg.is_user ? 0 : (map.size % 5) + 1);
    }
    return map;
  }
  function speakerLabel(seg) {
    if (seg.is_user) return seg.speaker_name || 'You';
    if (seg.speaker_name) return seg.speaker_name;
    const m = /(\d+)$/.exec(seg.speaker || '');
    return m ? 'Speaker ' + (+m[1]) : seg.speaker || 'Speaker';
  }

  function segmentRows(conv, audio, audioEl) {
    if (!conv || !(conv.segments || []).length) return [h('p', { class: 'empty' }, 'No transcript.')];
    const pal = speakerPalette(conv);
    const base = audio ? (ms(conv.started_at) - ms(audio.start)) / 1000 : 0;
    return conv.segments.map((seg) => {
      const idx = pal.get(seg.is_user ? '__user' : seg.speaker || seg.speaker_name || '?');
      const at = base + (seg.start || 0), end = base + (seg.end || seg.start || 0);
      return h('div', { class: 'seg' + (seg.is_user ? ' me' : ''), dataset: audio ? { t: at.toFixed(2), e: Math.max(end, at + 0.5).toFixed(2) } : {}, style: '--sc:var(--spk-' + idx + ')' },
        h('button', { class: 'ts', type: 'button', title: 'Play from here', disabled: !audioEl, onclick: () => { if (audioEl) { audioEl.currentTime = Math.max(0, at); audioEl.play().catch(() => {}); } } }, mmss(seg.start)),
        h('div', null,
          h('div', { class: 'spk' }, speakerLabel(seg), seg.is_user ? h('span', { class: 'you' }, 'OWNER') : null),
          h('p', null, seg.text || '')));
    });
  }

  function transcriptDiff(d) {
    const segs = (d.replay && d.replay.segments) || [];
    const B = [], segOf = [];
    segs.forEach((seg, i) => { for (const tok of tokens(seg.text)) { B.push(tok); segOf.push(i); } if (B.length) B[B.length - 1] = B[B.length - 1].replace(/\s*$/, ' '); });
    const A = tokens(((d.baseline && d.baseline.segments) || []).map((s) => s.text || '').join(' '));
    const ops = diffTokens(A, B);
    const pal = speakerPalette(d.replay);
    const paras = [];
    let cur = null, curSeg = -1;
    let ins = 0, del = 0;
    for (const op of ops) {
      if (op.b >= 0 && segOf[op.b] !== curSeg) {
        curSeg = segOf[op.b];
        const seg = segs[curSeg];
        cur = h('p');
        paras.push(h('div', { class: 'seg diffpara', style: '--sc:var(--spk-' + pal.get(seg.is_user ? '__user' : seg.speaker || seg.speaker_name || '?') + ')' }, h('div', { class: 'spk' }, speakerLabel(seg)), cur));
      }
      if (!cur) { cur = h('p'); paras.push(h('div', { class: 'seg diffpara' }, cur)); }
      if (op.t === 'eq') cur.append(op.s);
      else { cur.append(h(op.t === 'ins' ? 'ins' : 'del', null, op.s)); if (op.t === 'ins') ins++; else del++; }
    }
    paras.unshift(h('p', { class: 'pane-note', style: 'padding:0 12px' }, 'Word diff of the replay transcript against production: ', h('ins', null, ins + ' added'), ' ', h('del', null, del + ' removed'), ' words. Speaker labels are the replay’s.'));
    return paras;
  }

  function rightColumn(ctx) {
    const d = ctx.detail;
    const pairs = d.pairs;
    const counts = {
      summary: null,
      tasks: pairs.tasks.filter((p) => p.replay).length,
      memories: pairs.memories.filter((p) => p.replay).length,
      pushes: pairs.pushes.filter((p) => p.replay).length,
      calls: (d.llm_calls || []).length,
    };
    if (!d.replay) { counts.tasks = pairs.tasks.length; counts.memories = pairs.memories.length; counts.pushes = pairs.pushes.length; }
    const differs = {
      summary: (d.reasons || []).includes('summary'),
      tasks: pairs.tasks.some((p) => p.state !== 'same'),
      memories: pairs.memories.some((p) => p.state !== 'same'),
      pushes: pairs.pushes.some((p) => p.state !== 'same'),
      calls: false,
    };
    if (!TABS.some(([k]) => k === state.tab)) state.tab = 'summary';
    const panes = {};
    const tabBar = h('div', { class: 'tabs', role: 'tablist' }, TABS.map(([key, label]) => h('button', {
      type: 'button', role: 'tab', class: state.tab === key ? 'on' : '', dataset: { tab: key }, 'aria-selected': String(state.tab === key),
      onclick: () => setTab(key),
    }, label, counts[key] !== null ? h('span', { class: 'n' }, counts[key]) : null, differs[key] && d.replay && d.baseline ? h('span', { class: 'dot', title: 'differs vs production' }) : null)));
    const paneHost = h('div', { class: 'tabpane', role: 'tabpanel' });
    const builders = { summary: summaryPane, tasks: (c) => itemsPane(c, 'tasks'), memories: (c) => itemsPane(c, 'memories'), pushes: (c) => itemsPane(c, 'pushes'), calls: callsPane };
    function setTab(key) {
      state.tab = key;
      store.set('tab', key);
      $$('button', tabBar).forEach((b) => { b.classList.toggle('on', b.dataset.tab === key); b.setAttribute('aria-selected', String(b.dataset.tab === key)); });
      if (!panes[key]) panes[key] = builders[key](ctx);
      paneHost.replaceChildren(panes[key]);
      focusTarget(0, false);
    }
    ctx.setTab = setTab;
    for (const [key] of TABS) panes[key] = builders[key](ctx);
    paneHost.append(panes[state.tab]);
    return h('div', { class: 'card right-col' }, tabBar, paneHost);
  }

  function sideNone(label, text) { return h('div', { class: 'side none' }, h('span', { class: 'label' }, label), text); }

  function summaryPane(ctx) {
    const d = ctx.detail;
    const r = d.pairs.summary.replay, b = d.pairs.summary.baseline;
    const pane = h('div');
    const key = d.replay ? d.keys.replay.summary : d.keys.baseline.summary;
    const target = makeTarget(ctx, 'summary', key, 'Summary', (r || b || {}).title);
    const replaySide = d.replay
      ? (d.replay.discarded && !(r && r.title) ? sideNone('Replay', 'Discarded' + (d.replay.discard_reason ? ' (' + d.replay.discard_reason.replace(/_/g, ' ') + ')' : '') + ' — no summary.')
        : h('div', { class: 'side new' }, h('span', { class: 'label' }, 'Replay'),
          h('div', { class: 't' }, b ? diffSide(b.title || '', (r && r.title) || '', 'new') : (r && r.title) || ''),
          h('div', { class: 'ov' }, b ? diffSide(b.overview || '', (r && r.overview) || '', 'new') : (r && r.overview) || ''),
          r ? sectionsView(r.sections) : null,
          r ? h('div', { class: 'kv' }, r.category ? h('span', null, 'category: ' + r.category) : null, (r.events || []).length ? h('span', null, r.events.length + ' event(s)') : null, (r.participants || []).length ? h('span', null, 'people: ' + r.participants.map((x) => x.name || x).join(', ')) : null) : null))
      : sideNone('Replay', 'Not produced by the replay.');
    const prodSide = d.baseline
      ? (d.baseline.discarded && !(b && b.title) ? sideNone('Production', 'Discarded' + (d.baseline.discard_reason ? ' (' + d.baseline.discard_reason.replace(/_/g, ' ') + ')' : '') + ' — no summary.')
        : h('div', { class: 'side old' }, h('span', { class: 'label' }, 'Production'),
          h('div', { class: 't' }, r && d.replay ? diffSide((b && b.title) || '', r.title || '', 'old') : (b && b.title) || ''),
          h('div', { class: 'ov' }, r && d.replay ? diffSide((b && b.overview) || '', r.overview || '', 'old') : (b && b.overview) || ''),
          b ? sectionsView(b.sections) : null,
          b ? h('div', { class: 'kv' }, b.category ? h('span', null, 'category: ' + b.category) : null, (b.participants || []).length ? h('span', null, 'people: ' + b.participants.map((x) => x.name || x).join(', ')) : null) : null))
      : sideNone('Production', 'No production conversation (new in the replay).');
    const item = h('div', { class: 'item' },
      h('div', { class: 'item-top' }, h('span', { class: 'txt' }, h('span', { class: 'label' }, d.replay && d.baseline ? 'Replay beside production' : 'Summary'), d.replay && d.baseline && d.reasons.includes('summary') ? h('span', { class: 'vsprod' }, '  · differs vs production') : null), key ? verdictControls(target, verdictFor(target, d.verdicts)) : null),
      h('div', { class: 'summary-grid', style: 'margin-top:8px' }, replaySide, prodSide));
    const cur = verdictFor(target, d.verdicts);
    if (cur && cur.note) item.append(h('div', { class: 'note-line' }, cur.note));
    if (key) vt(item, target, 'summary');
    pane.append(item);
    const events = ((r && r.events) || []).concat([]);
    if (events.length) pane.append(h('div', { class: 'item' }, h('span', { class: 'label' }, 'Events'), h('ul', null, events.map((e) => h('li', null, e.title || e.description || JSON.stringify(e))))));
    return pane;
  }

  const ITEM_SPEC = {
    tasks: { kind: 'task', label: 'Task', text: (x) => x.description || '', sub: (x) => [x.due_at ? 'due ' + String(x.due_at).slice(0, 10) : null, x.completed ? 'completed' : null] },
    memories: { kind: 'memory', label: 'Memory', text: (x) => x.content || '', sub: (x) => [x.category || null] },
    pushes: { kind: 'notification', label: 'Push', text: (x) => (x.title ? x.title + ' — ' : '') + (x.body || ''), sub: (x) => [x.at ? clock(x.at) : null, x.trigger ? x.trigger.replace(/_/g, ' ') : null] },
  };

  function itemsPane(ctx, name) {
    const d = ctx.detail;
    const spec = ITEM_SPEC[name];
    const pairs = d.pairs[name];
    const pane = h('div');
    if (!pairs.length) { pane.append(h('p', { class: 'pane-note' }, 'None on either side.')); return pane; }
    const tally = { same: 0, changed: 0, added: 0, removed: 0 };
    pairs.forEach((p) => tally[p.state]++);
    if (d.replay && d.baseline) pane.append(h('p', { class: 'pane-note' }, [tally.same + ' same', tally.changed + ' changed', tally.added + ' only in replay', tally.removed + ' only in production'].join(' · '), h('span', { class: 'vsprod' }, '  (vs production)')));
    for (const p of pairs) {
      const item = p.replay || p.baseline;
      const target = makeTarget(ctx, spec.kind, p.key, spec.label, spec.text(item));
      const cur = verdictFor(target, d.verdicts);
      const tag = p.state === 'added' ? 'only in replay' : p.state === 'removed' ? 'only in production' : p.state;
      let body;
      if (p.state === 'changed') {
        body = [h('div', null, diffSide(spec.text(p.baseline), spec.text(p.replay), 'new')),
          h('div', { class: 'prodline' }, h('span', { class: 'label' }, 'production'), diffSide(spec.text(p.baseline), spec.text(p.replay), 'old'))];
      } else body = [h('div', null, spec.text(item))];
      const sub = spec.sub(item).filter(Boolean);
      const el = h('div', { class: 'item ' + p.state },
        h('div', { class: 'item-top' },
          h('div', { class: 'txt' }, body, sub.length ? h('div', { class: 'sub' }, sub.join(' · ')) : null),
          d.replay && d.baseline ? h('span', { class: 'chip ' + (p.state === 'same' ? 'st-same' : p.state === 'changed' ? 'st-changed' : 'st-' + p.state) }, tag) : null,
          verdictControls(target, cur)),
        cur && cur.note ? h('div', { class: 'note-line' }, cur.note) : null);
      vt(el, target, name);
      pane.append(el);
    }
    return pane;
  }

  function callsPane(ctx) {
    const calls = ctx.detail.llm_calls || [];
    const pane = h('div');
    if (!calls.length) { pane.append(h('p', { class: 'pane-note' }, ctx.detail.replay ? 'No LLM calls recorded for this conversation.' : 'Production calls are not recorded.')); return pane; }
    const total = calls.reduce((a, c) => a + (c.usd || 0), 0);
    const hits = calls.filter((c) => c.cache_hit).length;
    const tin = calls.reduce((a, c) => a + (c.tokens_in || 0), 0), tout = calls.reduce((a, c) => a + (c.tokens_out || 0), 0);
    pane.append(h('div', { class: 'calls-sum' }, h('span', null, calls.length + ' calls'), h('span', null, hits + ' cache hits'), h('span', { class: 'num' }, usd(total)), h('span', { class: 'num' }, tin.toLocaleString() + ' in / ' + tout.toLocaleString() + ' out tokens')));
    for (const c of calls) {
      pane.append(h('details', { class: 'call' },
        h('summary', null,
          h('span', { class: 'stage' }, c.stage || '—'),
          h('span', { class: 'model', title: (c.feature || '') + ' · ' + (c.model || '') }, (c.feature ? c.feature + ' · ' : '') + (c.model || '')),
          h('span', { class: 'chip ' + (c.cache_hit ? 'hit' : 'miss') }, c.cache_hit ? 'cache hit' : 'live'),
          h('span', { class: 'num tok' }, (c.tokens_in || 0) + '→' + (c.tokens_out || 0)),
          h('span', { class: 'num' }, usd(c.usd || 0))),
        h('div', { class: 'call-body' },
          h('div', { class: 'kv' }, h('span', null, 'id ' + c.id), c.ms !== undefined ? h('span', { class: 'ms' }, Math.round(c.ms) + ' ms') : null, c.at ? h('span', null, clock(c.at)) : null),
          promptView(c.prompt),
          h('div', { class: 'msg' }, h('span', { class: 'label' }, 'raw output'), h('pre', null, typeof c.output === 'string' ? c.output : JSON.stringify(c.output, null, 2))))));
    }
    return pane;
  }

  function promptView(prompt) {
    if (Array.isArray(prompt) && prompt.every((m) => m && typeof m === 'object' && 'role' in m)) {
      return prompt.map((m) => h('div', { class: 'msg' }, h('span', { class: 'label' }, m.role), h('pre', null, typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2))));
    }
    return h('div', { class: 'msg' }, h('span', { class: 'label' }, 'prompt'), h('pre', null, typeof prompt === 'string' ? prompt : JSON.stringify(prompt, null, 2)));
  }

  // ---------------------------------------------------------------- verdicts page

  const vfilters = store.get('vfilters', { kind: '', mark: '', run: '' });

  async function verdictsPage(token) {
    const q = new URLSearchParams();
    if (vfilters.kind) q.set('item_kind', vfilters.kind);
    if (vfilters.mark) q.set('mark', vfilters.mark);
    if (vfilters.run) q.set('run_id', vfilters.run);
    const data = await getJSON('/api/verdicts?' + q.toString());
    if (token !== state.renderToken) return null;
    const runs = state.runs || [];
    const sel = (key, options) => h('select', { 'aria-label': key, onchange: (e) => { vfilters[key] = e.target.value; store.set('vfilters', vfilters); render(); } },
      options.map(([v, label]) => h('option', { value: v, selected: vfilters[key] === v }, label)));
    const kinds = ['summary', 'task', 'memory', 'notification', 'boundary', 'speaker', 'transcript', 'daily_summary'];
    const rows = data.verdicts || [];
    const counts = { good: rows.filter((r) => r.mark === 'good').length, bad: rows.filter((r) => r.mark === 'bad').length };
    const head = h('div', { class: 'vpage-head' },
      h('h1', null, 'Verdicts'),
      sel('kind', [['', 'All kinds']].concat(kinds.map((k) => [k, k.replace('_', ' ')]))),
      sel('mark', [['', 'Good and bad'], ['good', 'Good'], ['bad', 'Bad']]),
      sel('run', [['', 'All runs']].concat(runs.map((r) => [r.run_id, r.run_id]))),
      h('span', { class: 'meta' }, h('span', { class: 'mark good' }, counts.good + ' good'), h('span', { class: 'mark bad' }, counts.bad + ' bad')),
      h('span', { class: 'spacer', style: 'flex:1' }),
      h('a', { class: 'btn', href: '/api/verdicts/export?' + q.toString(), download: 'verdicts.jsonl', style: 'display:inline-flex;align-items:center' }, 'Export JSONL'));
    if (!rows.length) return h('div', null, head, h('p', { class: 'empty' }, 'No verdicts yet. Mark items with 1 / 2 on a conversation page.'));
    const tz = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    return h('div', null, head, h('div', { class: 'card' }, h('table', { class: 'vtable' },
      h('thead', null, h('tr', null, h('th', null, 'Mark'), h('th', null, 'Kind'), h('th', null, 'Item'), h('th', null, 'Note'), h('th', { class: 'runcol' }, 'Run'), h('th', { class: 'when' }, 'When'))),
      h('tbody', null, rows.map((v) => {
        const href = v.conversation_id ? '#/run/' + encodeURIComponent(v.run_id) + '/c/' + encodeURIComponent(v.conversation_id) : '#/run/' + encodeURIComponent(v.run_id);
        return h('tr', null,
          h('td', null, h('span', { class: 'mark ' + v.mark }, v.mark === 'good' ? '👍 good' : '👎 bad')),
          h('td', null, (v.item_kind || '').replace('_', ' ')),
          h('td', { class: 'what' }, h('a', { href }, snapshotText(v.item_snapshot) || v.item_key), v.item_snapshot && v.item_snapshot.side === 'production' ? h('span', { class: 'vsprod' }, '  production side') : null),
          h('td', { class: 'note' }, v.note || ''),
          h('td', { class: 'runcol' }, h('code', null, v.ref || ''), h('div', { class: 'vsprod' }, v.run_id)),
          h('td', { class: 'when' }, v.at ? tz.format(new Date(v.at)) : ''));
      })))));
  }

  function snapshotText(snap) {
    if (!snap) return '';
    const v = snap.value !== undefined ? snap.value : snap;
    if (typeof v === 'string') return v;
    if (!v || typeof v !== 'object') return '';
    if (v.started_at && v.finished_at) return 'Boundary ' + clock(v.started_at) + '–' + clock(v.finished_at);
    if (v.speakers) return 'Speakers: ' + v.speakers.join(', ');
    return v.description || v.content || (v.title && v.body ? v.title + ' — ' + v.body : '') || v.title || v.overview || v.text || JSON.stringify(v).slice(0, 160);
  }

  // ---------------------------------------------------------------- keyboard

  document.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
    if (document.querySelector('dialog[open]')) return;
    const route = state.route || {};
    const key = e.key;
    if (key === '?') { e.preventDefault(); $('#help-dialog').showModal(); return; }
    if (key === 'v') { location.hash = '#/verdicts'; return; }
    if (route.view === 'day') {
      if (key === 'j' || key === 'k') { e.preventDefault(); moveSelection(key === 'j' ? 1 : -1); }
      else if (key === 'Enter' || key === 'o') {
        const sel = state.selected.get(route.runId);
        const el = sel && $('.crow[data-key="' + CSS.escape(sel) + '"]');
        if (el) { e.preventDefault(); location.hash = el.getAttribute('href'); }
      } else if (key === '/') { e.preventDefault(); const s = $('#conv-search'); if (s) { s.focus(); s.select(); } }
      return;
    }
    if (route.view === 'conv') {
      const nav = state.nav || {};
      if (key === 'j' || key === 'k') {
        const to = key === 'j' ? nav.next : nav.prev;
        if (to) { e.preventDefault(); location.hash = convHref(route.runId, to); }
      } else if (key === 'Escape' || key === 'u') {
        e.preventDefault(); location.hash = '#/run/' + encodeURIComponent(route.runId);
      } else if (key === '/') {
        e.preventDefault(); location.hash = '#/run/' + encodeURIComponent(route.runId);
        setTimeout(() => { const s = $('#conv-search'); if (s) s.focus(); }, 120);
      } else if (key === 'ArrowDown' || key === 'ArrowUp') {
        e.preventDefault(); focusTarget(state.focus + (key === 'ArrowDown' ? 1 : -1));
      } else if (key === 'ArrowRight' || key === 'ArrowLeft' || key === ']' || key === '[') {
        e.preventDefault();
        const i = TABS.findIndex(([k]) => k === state.tab);
        const ni = (i + (key === 'ArrowRight' || key === ']' ? 1 : -1) + TABS.length) % TABS.length;
        const btn = $('.tabs button[data-tab="' + TABS[ni][0] + '"]');
        if (btn) btn.click();
      } else if (key === '1' || key === '2') {
        const t = focusedTarget();
        if (t) { e.preventDefault(); submitVerdict(t, key === '1' ? 'good' : 'bad', t.current ? t.current.note : ''); }
        else toast('Nothing to mark in this tab');
      } else if (key === 'n') {
        const t = focusedTarget();
        if (t) { e.preventDefault(); openNote(t); }
      } else if (key === ' ') {
        const a = $('#player');
        if (a) { e.preventDefault(); if (a.paused) a.play().catch(() => {}); else a.pause(); }
      } else if (key === 't') {
        const btns = $$('.tr-head .seg-toggle button');
        if (btns.length > 1) {
          const i = btns.findIndex((b) => b.classList.contains('on'));
          btns[(i + 1) % btns.length].click();
        }
      }
    }
  });

  window.addEventListener('hashchange', render);
  render();
})();
