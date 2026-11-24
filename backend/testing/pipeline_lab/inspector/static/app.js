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
    dayFilter: null,
    search: '',
    selected: new Map(), // run -> conversation key selected on the day page
    tab: store.get('tab', 'summary'),
    trMode: 'replay',
    follow: store.get('follow', true),
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
    if (!raw.includes('?')) {
      // Some launchers percent-encode the fragment's "?": the first encoded one separates path from query.
      const at = raw.search(/%3F/i);
      if (at >= 0) raw = raw.slice(0, at) + '?' + raw.slice(at + 3);
    }
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
    if (route.runId) state.lastRun = route.runId;
    setNav(route);
    app.classList.add('loading');
    try {
      const runs = await loadRuns();
      if (token !== state.renderToken) return;
      updateRunSelect(runs, route.runId);
      setNav(route);
      let view;
      if (route.view === 'home') {
        if (runs.length) { location.replace('#/run/' + encodeURIComponent(runs[0].run_id)); return; }
        view = emptyStore();
      } else if (route.view === 'day') view = await dayPage(route, token);
      else if (route.view === 'conv') view = await convPage(route, token);
      else view = await verdictsPage(token);
      if (token !== state.renderToken || !view) return;
      app.classList.remove('loading');
      app.replaceChildren(view);
      if (route.view === 'day') {
        restoreSelection(route.runId, prev);
      } else {
        window.scrollTo(0, 0);
      }
      if (route.view === 'conv') focusTarget(0, false);
    } catch (err) {
      if (token !== state.renderToken) return;
      app.classList.remove('loading');
      app.replaceChildren(h('p', { class: 'empty error' }, 'Could not load: ' + err.message));
    }
  }

  /* Nav state is a pure function of the route (and the last run seen), set before anything loads, so
     Day / Verdicts always show where you are and Day always leads back to the day you came from. */
  function dayHref(route, lastRun, runs) {
    const runId = (route && route.runId) || (lastRun && (!runs || runs.some((r) => r.run_id === lastRun)) ? lastRun : runs && runs[0] && runs[0].run_id);
    return runId ? '#/run/' + encodeURIComponent(runId) : '#/';
  }
  function setNav(route) {
    const day = $('#nav-day'), verdicts = $('#nav-verdicts');
    const onDay = route.view === 'day' || route.view === 'conv';
    day.classList.toggle('on', onDay);
    verdicts.classList.toggle('on', route.view === 'verdicts');
    if (onDay) day.setAttribute('aria-current', 'page'); else day.removeAttribute('aria-current');
    if (route.view === 'verdicts') verdicts.setAttribute('aria-current', 'page'); else verdicts.removeAttribute('aria-current');
    day.setAttribute('href', dayHref(route, state.lastRun, state.runs));
  }
  function updateRunSelect(runs, current) {
    const sel = $('#run-select');
    const runId = current || (state.lastRun && runs.some((r) => r.run_id === state.lastRun) ? state.lastRun : runs[0] && runs[0].run_id);
    sel.replaceChildren(...runs.map((r) => h('option', { value: r.run_id, selected: r.run_id === runId }, (r.date || r.day_id) + ' · ' + shortRef(r) + ' · ' + r.run_id)));
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

  /* Group kinds from baseline/compare.py. A conversation's status word is its group's kind. */
  const KIND_LABEL = {
    same: 'same', cosmetic: 'cosmetic only', content: 'changed', changed: 'changed', merge: 'merged', split: 'split',
    regroup: 'regrouped', new: 'new', missing: 'missing', merged: 'merged', 'discard flipped': 'discard flipped',
  };
  const KIND_TITLE = {
    same: 'Same as production', cosmetic: 'Only emoji, category, hidden reason or punctuation differ', content: 'Title, overview, tasks, memories, pushes, events, edges or Home differ',
    merge: 'Several production conversations became one replay conversation', split: 'One production conversation became several replay conversations',
    regroup: 'Production and replay cut this stretch into different conversations', new: 'Only the replay has this', missing: 'Only production has this',
  };
  const STATUS_CLASS = {
    same: 'st-same', cosmetic: 'st-same', changed: 'st-changed', content: 'st-changed', new: 'st-new', missing: 'st-missing',
    merge: 'st-merged', split: 'st-merged', regroup: 'st-merged', merged: 'st-merged', 'discard flipped': 'st-flipped',
  };
  function statusChip(status, withVs) {
    return h('span', { class: 'chip ' + (STATUS_CLASS[status] || ''), title: KIND_TITLE[status] || '' }, KIND_LABEL[status] || status,
      withVs && status !== 'same' && status !== 'new' ? h('span', { class: 'vsprod' }, ' vs production') : null);
  }

  /* Home hidden reasons in plain words (v3 home_hidden_reason, classic discard reasons). */
  const REASON_WORDS = {
    below_word_minimum: 'too short', media: 'media playing', background_wearer_recognized: 'background, wearer not talking',
    background: 'background', discarded: 'discarded', hidden: 'hidden', conversation: 'hidden',
  };
  function reasonWords(reason) { return REASON_WORDS[reason] || String(reason || 'hidden').replace(/_/g, ' '); }

  function dayFilter() {
    if (!state.dayFilter) state.dayFilter = Object.assign({ tag: null, view: 'worth', sort: 'time' }, store.get('dayFilter', {}));
    return state.dayFilter;
  }

  async function dayPage(route, token) {
    const ov = await loadOverview(route.runId, true);
    if (token !== state.renderToken) return null;
    TZ = ov.day.timezone || 'UTC';
    if (!ov.groups) return h('p', { class: 'empty error' }, 'This server runs older inspector code than this page. Restart the inspector server to load the new day view.');
    const panel = h('aside', { class: 'day-panel', 'aria-label': 'Day panel' }, h('div', { class: 'card' }, h('p', { class: 'empty' }, 'Loading day panel…')));
    const page = h('div', { class: 'page day' + (store.get('panel', true) ? '' : ' panel-closed') });
    const body = dayBody(ov, route.runId, page);
    page.append(dayHeader(ov), body.digest, h('div', { class: 'day-grid' }, body.list, panel));
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

  function audioBadge(cov) {
    const gaps = cov.gaps && cov.gaps.length ? ' · ' + cov.gaps.length + ' gap' + (cov.gaps.length === 1 ? '' : 's') : '';
    if (!cov.with_audio) return h('span', { class: 'chip', title: 'No audio files are in this corpus day, so the player is off. Transcripts came from storage.' }, 'no audio loaded' + gaps);
    return h('span', { class: 'chip', title: (cov.audio_seconds ? dur(cov.audio_seconds) + ' of audio. ' : '') + 'Conversations with an audio clip / all conversations of the day.' },
      'audio ' + cov.with_audio + '/' + (cov.conversations || 0) + gaps);
  }

  function dayHeader(ov) {
    const run = ov.run;
    const cov = ov.day.coverage || {};
    const overlay = flatten(run.overlay);
    const spendPct = run.budget_usd ? Math.min(100, (100 * (run.spend_usd || 0)) / run.budget_usd) : 0;
    const items = [
      h('span', { class: 'item', title: 'ref under test' + (run.commit ? ' · ' + run.commit : '') }, h('span', { class: 'label' }, 'ref'), h('code', null, shortRef(run))),
      run.pipeline === 'v3' ? h('span', { class: 'chip', title: 'Conversations v3: the day\'s recordings were fed to the real v3 builder. Production is its v3 result for the day.' }, 'pipeline v3') : null,
      run.stt ? h('span', { class: 'item', title: 'where the transcripts came from' }, h('span', { class: 'label' }, 'stt'), run.stt) : null,
      run.engine === 'fake' ? h('span', { class: 'chip badge-warn', title: 'Plumbing check: a stand-in replaced the product pipeline' }, 'engine: fake') : null,
      h('span', { class: 'item spend', title: 'spend vs cap' }, h('span', { class: 'label' }, 'spend'), h('span', { class: 'num' }, usd(run.spend_usd) + ' / ' + usd(run.budget_usd)), h('span', { class: 'meter' + (spendPct > 80 ? ' hot' : '') }, h('i', { style: 'width:' + spendPct.toFixed(1) + '%' }))),
      h('span', { class: 'item' }, h('span', { class: 'label' }, 'wall'), h('span', { class: 'num' }, dur(run.wall_seconds))),
      run.status && run.status !== 'complete' ? h('span', { class: 'chip badge-warn' }, run.status) : null,
      run.start_state === 'approximate' ? h('span', { class: 'chip badge-warn', title: 'Start state comes from a snapshot taken after the day began' }, 'start state: approximate') : null,
      audioBadge(cov),
      h('details', { class: 'inline item' },
        h('summary', null, h('span', { class: 'label' }, 'overlay'), ' ', overlay.length ? overlay.length + ' ▾' : 'none'),
        overlay.length ? h('div', { class: 'pop' }, h('table', null, overlay.map(([k, v]) => h('tr', null, h('td', null, k), h('td', null, v))))) : null),
      (run.warnings || []).length ? h('details', { class: 'inline item warn' }, h('summary', null, run.warnings.length + ' warning' + (run.warnings.length === 1 ? '' : 's') + ' ▾'), h('div', { class: 'pop' }, h('ul', null, run.warnings.map((w) => h('li', null, w))))) : null,
    ];
    return h('div', { class: 'day-head' },
      h('h1', null, longDate(ov.day.date), h('span', { class: 'tz' }, ov.day.timezone || 'UTC')),
      h('div', { class: 'meta' }, items));
  }

  /* The "What changed" lines. Every chip number is digest.tags[tag]: the count of groups with that tag,
     which is exactly what the list shows when the chip is on. */
  const DIGEST = [
    ['home', 'Home', (d) => ['production ', h('b', null, d.home.production), ' → replay ', h('b', null, d.home.replay), ' on Home'],
      [['home_dropped', 'dropped off Home', 'bad'], ['home_added', 'newly on Home', 'good'], ['home_both', 'on Home in both', '']]],
    ['grouping', 'Grouping', (d) => ['production ', h('b', null, d.conversations.production), ' → replay ', h('b', null, d.conversations.replay), ' conversations'],
      [['merge', 'merged'], ['split', 'split'], ['regroup', 'regrouped'], ['new', 'new'], ['missing', 'missing'], ['boundary', 'edges moved']]],
    ['content', 'Content', () => [],
      [['summary', 'summary rewritten'], ['events', 'events differ'], ['tasks', 'tasks differ'], ['memories', 'memories differ'], ['pushes', 'pushes differ'], ['transcript', 'transcript differs'], ['discard', 'discard flipped']]],
    ['cosmetic', 'Cosmetic', () => [h('span', { class: 'faint' }, 'not counted as changed')],
      [['cosmetic', 'emoji / category / punctuation only'], ['same', 'identical']]],
  ];
  const TAG_LABEL = Object.fromEntries(DIGEST.flatMap((line) => line[3].map(([tag, label]) => [tag, label])));
  TAG_LABEL.worth = 'worth a look';

  function groupOpen(runId, g) { return convHref(runId, g.open); }
  function groupTitles(g) { return g.production.concat(g.replay).map((c) => (c.title || '') + ' ' + (c.emoji || '')).join(' ') + ' ' + g.change; }

  function visibleGroups(ov) {
    const f = dayFilter();
    const q = state.search.trim().toLowerCase();
    let groups = ov.groups.filter((g) => (f.tag ? g.tags.includes(f.tag) : f.view === 'all' || g.tags.includes('worth')));
    if (q) groups = groups.filter((g) => groupTitles(g).toLowerCase().includes(q));
    if (f.sort === 'diff') groups = groups.slice().sort((a, b) => b.score - a.score || (a.started_at || '').localeCompare(b.started_at || ''));
    return groups;
  }

  /* Conversations in list order, for j/k on the conversation page. */
  function openables(ov) {
    const out = [];
    for (const g of visibleGroups(ov)) {
      if (g.replay.length) for (const c of g.replay) out.push({ kind: 'replay', id: c.id, group: g.id });
      else out.push({ kind: 'production', id: g.production[0].id, group: g.id });
    }
    return out;
  }

  function dayBody(ov, runId, page) {
    const f = dayFilter();
    const d = ov.digest;
    const save = () => store.set('dayFilter', { view: f.view, sort: f.sort });
    const chipEls = [];
    const digest = h('section', { class: 'card digest', 'aria-label': 'What changed' },
      h('div', { class: 'dg-head' }, h('span', { class: 'label' }, 'What changed'), h('span', { class: 'faint' }, d.groups + ' pairing groups · every number filters the list')),
      DIGEST.map(([key, label, lead, chips]) => h('div', { class: 'dg-line dg-' + key },
        h('span', { class: 'dg-label' }, label),
        h('span', { class: 'dg-lead' }, lead(d)),
        h('span', { class: 'dg-chips' }, chips.map(([tag, text, tone]) => {
          if ((tag === 'discard' || tag === 'regroup') && !d.tags[tag]) return null;
          const btn = h('button', {
            type: 'button', class: 'dchip' + (tone ? ' ' + tone : '') + (d.tags[tag] ? '' : ' zero'), dataset: { tag }, 'aria-pressed': 'false',
            onclick: () => { f.tag = f.tag === tag ? null : tag; fill(); },
          }, h('b', null, d.tags[tag] || 0), ' ', text);
          chipEls.push(btn);
          return btn;
        })))));

    const viewToggle = h('span', { class: 'seg-toggle', role: 'group', 'aria-label': 'View' },
      [['worth', 'Worth a look', d.tags.worth], ['all', 'Everything', d.groups]].map(([v, text, n]) => h('button', {
        type: 'button', dataset: { view: v }, title: v === 'worth' ? 'Home flips, grouping changes and substantive content changes' : 'Every group, cosmetic and identical ones included',
        onclick: () => { f.view = v; f.tag = null; save(); fill(); },
      }, text, h('span', { class: 'n' }, n))));
    const sortToggle = h('span', { class: 'seg-toggle', role: 'group', 'aria-label': 'Sort' },
      [['time', 'Time'], ['diff', 'Most different']].map(([v, text]) => h('button', {
        type: 'button', dataset: { sort: v }, title: v === 'diff' ? 'Home flip, then grouping change, then size of the title / overview edit, then item counts' : 'Time of day',
        onclick: () => { f.sort = v; save(); fill(); },
      }, text)));
    const search = h('input', { class: 'search', id: 'conv-search', type: 'search', placeholder: 'Filter by title  ( / )', value: state.search, 'aria-label': 'Filter conversations',
      oninput: (e) => { state.search = e.target.value; fill(); },
      onkeydown: (e) => { if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); e.target.blur(); } } });
    const panelBtn = h('button', { type: 'button', class: 'btn panel-btn', title: 'Show or hide the day panel (daily summary, goals, memories, pushes)',
      onclick: () => { const open = page.classList.toggle('panel-closed') === false; store.set('panel', open); } }, 'Day panel');
    const statEl = h('p', { class: 'statline' });
    const listEl = h('div', { class: 'pl-body', role: 'listbox', 'aria-label': 'Conversations, production beside replay' });
    const head = h('div', { class: 'pl-head' },
      h('span', { class: 'pl-side' }, 'Production', h('small', null, 'what the phone got')),
      h('span', { class: 'pl-gut', title: 'Time runs down. Left lane production, right lane replay; a filled block is on Home.' }, 'time'),
      h('span', { class: 'pl-side' }, 'Replay', h('small', null, shortRef(ov.run))));

    function fill() {
      const groups = visibleGroups(ov);
      for (const btn of chipEls) { const on = f.tag === btn.dataset.tag; btn.classList.toggle('on', on); btn.setAttribute('aria-pressed', String(on)); }
      $$('button', viewToggle).forEach((b) => b.classList.toggle('on', !f.tag && b.dataset.view === f.view));
      $$('button', sortToggle).forEach((b) => b.classList.toggle('on', b.dataset.sort === f.sort));
      statEl.replaceChildren();
      const what = f.tag ? TAG_LABEL[f.tag] : f.view === 'worth' ? 'worth a look' : 'all groups';
      append(statEl, [h('b', null, groups.length), ' group' + (groups.length === 1 ? '' : 's') + ' · ' + what,
        state.search.trim() ? ' · matching “' + state.search.trim() + '”' : null,
        f.tag ? [' · ', h('button', { type: 'button', class: 'linkish', onclick: () => { f.tag = null; fill(); } }, 'clear filter')] : null]);
      listEl.replaceChildren(...(groups.length ? groupRows(groups, ov, runId, f.sort === 'time') : [h('p', { class: 'empty' }, 'Nothing here.')]));
      const sel = state.selected.get(runId);
      if (sel) markSelected(sel, false);
    }
    fill();
    const list = h('section', { class: 'paired', 'aria-label': 'Conversations' },
      h('div', { class: 'toolbar' }, viewToggle, sortToggle, search, h('span', { class: 'spacer' }), panelBtn), statEl, h('div', { class: 'card pl' }, head, listEl));
    return { digest, list };
  }

  const hourOf = (iso) => (iso ? fmt({ hour: '2-digit', hourCycle: 'h23' }).format(new Date(iso)) : '');

  function groupRows(groups, ov, runId, timeOrder) {
    const out = [];
    // A gap is worth a tick only when some audio exists and the gap is shorter than half a day.
    const cov = ov.day.coverage || {};
    const gaps = cov.with_audio ? ((ov.timeline && ov.timeline.gaps) || []).filter((x) => ms(x.end) - ms(x.start) < 43200000) : [];
    let prevEnd = null, prevHour = null;
    for (const g of groups) {
      if (timeOrder) {
        const hour = hourOf(g.started_at);
        const quiet = prevEnd ? (ms(g.started_at) - ms(prevEnd)) / 1000 : 0;
        const between = prevEnd ? gaps.filter((x) => ms(x.end) > ms(prevEnd) && ms(x.start) < ms(g.started_at)) : [];
        if (hour !== prevHour || quiet >= 1800 || between.length) {
          out.push(h('div', { class: 'tick', 'aria-hidden': 'true' },
            h('span', { class: 'tick-label' }, hour !== prevHour ? hour + ':00' : clock(g.started_at)),
            quiet >= 1200 ? h('span', { class: 'tick-quiet' }, dur(quiet) + ' quiet') : null,
            between.length ? h('span', { class: 'tick-gap' }, 'no audio ' + between.map((x) => clock(x.start) + '–' + clock(x.end)).join(', ')) : null));
          prevHour = hour;
        }
        if (!prevEnd || ms(g.finished_at) > ms(prevEnd)) prevEnd = g.finished_at;
      }
      out.push(groupRow(g, runId));
    }
    return out;
  }

  function lanes(g) {
    const a = ms(g.started_at), b = ms(g.finished_at);
    const span = Math.max(1, b - a);
    const blocks = (cells) => cells.map((c) => {
      const top = Math.max(0, ((ms(c.started_at) - a) / span) * 100);
      const height = Math.max(4, ((ms(c.finished_at || c.started_at) - ms(c.started_at)) / span) * 100);
      return h('i', { class: c.home ? 'on' : '', style: 'top:' + top.toFixed(1) + '%;height:' + Math.min(100 - top, height).toFixed(1) + '%', title: clock(c.started_at) + '–' + clock(c.finished_at) + (c.home ? ' · on Home' : ' · hidden') });
    });
    return h('span', { class: 'lanes' }, h('span', { class: 'lane' }, blocks(g.production)), h('span', { class: 'lane' }, blocks(g.replay)));
  }

  function homeState(c) {
    if (c.home) return h('span', { class: 'home-pill', title: 'Visible on the phone\'s Home list' }, 'HOME');
    return h('span', { class: 'hidden-note', title: 'Not on Home: ' + (c.home_reason || 'hidden') }, 'hidden · ' + reasonWords(c.home_reason));
  }

  function cell(c, href, runId) {
    const counts = [];
    if (c.counts.tasks) counts.push(c.counts.tasks + ' task' + (c.counts.tasks === 1 ? '' : 's'));
    if (c.counts.memories) counts.push(c.counts.memories + ' mem');
    if (c.counts.pushes) counts.push(c.counts.pushes + ' push' + (c.counts.pushes === 1 ? '' : 'es'));
    if (c.recordings > 1) counts.push(c.recordings + ' rec');
    const marks = [];
    for (let i = 0; i < (c.verdicts.good || 0); i++) marks.push(h('i', { class: 'good' }));
    for (let i = 0; i < (c.verdicts.bad || 0); i++) marks.push(h('i', { class: 'bad' }));
    return h('a', { class: 'cell' + (c.home ? ' home' : ' off'), href, dataset: { key: (c.side === 'production' ? 'p:' : 'c:') + c.id },
      onclick: (e) => { e.stopPropagation(); state.selected.set(runId, 'c:' + c.id); } },
    h('span', { class: 'c-top' }, h('time', { class: 'ts' }, clock(c.started_at)), h('span', { class: 'dur' }, dur(c.duration)), homeState(c),
      marks.length ? h('span', { class: 'vdots', title: 'verdicts' }, marks) : null),
    h('span', { class: 'c-title' }, c.emoji ? h('span', { class: 'emoji', 'aria-hidden': 'true' }, c.emoji) : null,
      h('span', { class: 't' }, c.title || (c.discarded ? 'Discarded' : 'Untitled'))),
    counts.length || c.backfilled ? h('span', { class: 'c-counts' }, counts.join(' · '), c.backfilled ? h('span', { class: 'faint', title: 'Production made this row in a backfill pass, not live' }, (counts.length ? ' · ' : '') + 'backfilled') : null) : null);
  }

  function groupRow(g, runId) {
    const open = groupOpen(runId, g);
    const flip = g.tags.includes('home_dropped') ? ' flip-drop' : g.tags.includes('home_added') ? ' flip-add' : '';
    const quiet = g.kind === 'same' || g.kind === 'cosmetic';
    return h('div', {
      class: 'grp k-' + g.kind + flip + (quiet ? ' quiet' : ''), role: 'option', dataset: { key: 'g:' + g.id, gid: g.id },
      onclick: (e) => { if (e.target.closest('a')) return; state.selected.set(runId, 'g:' + g.id); location.hash = open; },
    },
    h('div', { class: 'side prod' }, g.production.length ? g.production.map((c) => cell(c, open, runId)) : h('span', { class: 'cell empty' }, 'not in production')),
    h('div', { class: 'gut' }, h('span', { class: 'mk', title: KIND_TITLE[g.kind] || g.kind }, g.marker), lanes(g)),
    h('div', { class: 'side rep' },
      g.replay.length ? g.replay.map((c) => cell(c, convHref(runId, { kind: 'replay', id: c.id }), runId)) : h('span', { class: 'cell empty' }, 'not in replay'),
      h('span', { class: 'change' + (quiet ? ' cosm' : '') }, g.change)));
  }

  function markSelected(key, scroll) {
    $$('.grp.sel').forEach((el) => el.classList.remove('sel'));
    let el = null;
    if (key.startsWith('g:')) el = $('.grp[data-key="' + CSS.escape(key) + '"]');
    else {
      const cellEl = $('.cell[data-key="' + CSS.escape(key) + '"]') || $('.cell[data-key="' + CSS.escape('p:' + key.slice(2)) + '"]');
      el = cellEl && cellEl.closest('.grp');
    }
    if (el) {
      el.classList.add('sel');
      if (scroll) el.scrollIntoView({ block: 'nearest' });
    }
  }

  function restoreSelection(runId, prev) {
    let key = state.selected.get(runId);
    if (prev && prev.view === 'conv' && prev.runId === runId) key = 'c:' + prev.id;
    if (!key) return;
    state.selected.set(runId, key);
    markSelected(key, true);
  }

  function moveSelection(delta) {
    const els = $$('.grp');
    if (!els.length) return;
    let idx = els.findIndex((el) => el.classList.contains('sel'));
    idx = idx < 0 ? (delta > 0 ? 0 : els.length - 1) : Math.max(0, Math.min(els.length - 1, idx + delta));
    state.selected.set(state.route.runId, els[idx].dataset.key);
    markSelected(els[idx].dataset.key, true);
  }

  function openSelection() {
    const el = $('.grp.sel');
    if (!el) return false;
    const ov = state.overview.get(state.route.runId);
    const g = ov && ov.groups.find((x) => x.id === el.dataset.gid);
    if (g) location.hash = groupOpen(state.route.runId, g);
    return !!g;
  }

  async function loadDayPanel(runId, panel) {
    try {
      if (!state.dayPanel.has(runId)) state.dayPanel.set(runId, await getJSON('/api/runs/' + encodeURIComponent(runId) + '/day'));
      const d = state.dayPanel.get(runId);
      panel.replaceChildren(dailySummaryCard(d, runId), goalsCard(d), memoryDeltaCard(d.memory_delta), pushLogCard(d.notifications));
    } catch (err) {
      panel.replaceChildren(h('div', { class: 'card' }, h('p', { class: 'error' }, 'Day panel: ' + err.message)));
    }
  }

  function highlightText(x) {
    if (!x || typeof x !== 'object') return String(x);
    return [x.emoji, x.topic].filter(Boolean).join(' ') + (x.summary ? (x.topic ? ' — ' : '') + x.summary : '');
  }

  function summarySide(label, value, other, side, failure) {
    if (!value) {
      if (failure) return h('div', { class: 'side none failed' }, h('span', { class: 'label' }, label), h('span', { class: 'error' }, 'Failed'), h('div', { class: 'sub' }, failure));
      return h('div', { class: 'side none' }, h('span', { class: 'label' }, label), 'none');
    }
    const o = other || { title: '', overview: '', highlights: [] };
    const hasOther = !!other;
    const otherTexts = (o.highlights || []).map(highlightText);
    return h('div', { class: 'side ' + side },
      h('span', { class: 'label' }, label),
      value.title ? h('div', { class: 't' }, hasOther ? diffSide(side === 'new' ? o.title : value.title, side === 'new' ? value.title : o.title, side) : value.title) : null,
      value.overview ? h('p', null, hasOther ? diffSide(side === 'new' ? o.overview : value.overview, side === 'new' ? value.overview : o.overview, side) : value.overview) : null,
      value.highlights && value.highlights.length ? h('ul', { class: 'highlights' }, value.highlights.map((x) => {
        const text = highlightText(x);
        const only = hasOther && !otherTexts.includes(text);
        return h('li', null, only ? h(side === 'new' ? 'ins' : 'del', null, text) : text);
      })) : null);
  }

  function dailySummaryCard(d, runId) {
    const ds = d.daily_summary || {};
    const target = ds.key ? { kind: 'daily_summary', key: ds.key, conversation_id: null, label: 'Daily summary', runId } : null;
    const v = target ? verdictFor(target, ds.verdicts || []) : null;
    return h('section', { class: 'card' },
      h('div', { class: 'section-title' }, 'Daily summary', h('span', { class: 'spacer' }), target ? verdictControls(target, v) : null),
      h('div', { class: 'pair-cols stacked' }, summarySide('Replay', ds.replay, ds.baseline, 'new', ds.replay_failure), summarySide('Production', ds.baseline, ds.replay, 'old')),
      v && v.note ? h('div', { class: 'item' }, h('div', { class: 'note-line' }, v.note)) : null);
  }

  const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });
  const plain = new Intl.NumberFormat('en', { maximumFractionDigits: 2 });
  function goalNum(x, g) {
    if (typeof x !== 'number') return '—';
    const unit = (g.unit || '').toLowerCase();
    if (g.target === 1 && x >= 0 && x <= 1 && !unit) return Math.round(x * 100) + '%';
    const n = Math.abs(x) >= 10000 ? compact.format(x) : plain.format(x);
    if (unit === 'dollars' || unit === 'usd' || unit === '$') return '$' + n;
    if (unit === 'percent' || unit === '%') return n + '%';
    return unit ? n + ' ' + unit : n;
  }

  function goalsCard(d) {
    const goals = d.goals || [];
    const changed = goals.filter((g) => g && g.changed);
    const showAll = !!state.allGoals;
    const shown = showAll ? goals : changed;
    const card = h('section', { class: 'card' }, h('div', { class: 'section-title' }, 'Goals', h('span', { class: 'label' }, changed.length + ' changed of ' + goals.length),
      h('span', { class: 'spacer' }),
      goals.length && goals.length !== changed.length ? h('button', { type: 'button', class: 'linkish', onclick: () => { state.allGoals = !showAll; card.replaceWith(goalsCard(d)); } }, showAll ? 'changed only' : 'show all') : null));
    if (!shown.length) { card.append(h('p', { class: 'pane-note' }, goals.length ? 'No goal moved during the replayed day.' : 'No goals.')); return card; }
    for (const g of shown) {
      const target = typeof g.target === 'number' && g.target > 0 ? g.target : null;
      const pct = (x) => (target && typeof x === 'number' ? Math.min(100, (100 * x) / target) : 0);
      card.append(h('div', { class: 'goal' + (g.changed ? '' : ' still') },
        h('span', null, g.title || g.name || 'Goal'),
        h('span', { class: 'num' }, goalNum(g.progress_before, g) + ' → ' + goalNum(g.progress_after, g) + (target && target !== 1 ? ' of ' + goalNum(target, g) : '')),
        target ? h('div', { class: 'bar' }, h('i', { class: 'after', style: 'width:' + pct(g.progress_after) + '%' }), h('i', { class: 'before', style: 'width:' + pct(g.progress_before) + '%' })) : null,
        g.note ? h('span', { class: 'note' }, g.note) : null));
    }
    return card;
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
    state.selected.set(route.runId, 'c:' + route.id);
    const same = (r) => r.kind === route.kind && r.id === route.id;
    let rows = ov.groups ? openables(ov) : [];
    let idx = rows.findIndex(same);
    if (idx < 0 && ov.groups) { const all = Object.assign({}, dayFilter()); state.dayFilter = Object.assign({}, all, { tag: null, view: 'all' }); rows = openables(ov); state.dayFilter = all; idx = rows.findIndex(same); }
    const prev = idx > 0 ? rows[idx - 1] : null, next = idx >= 0 && idx < rows.length - 1 ? rows[idx + 1] : null;
    state.nav = { prev, next };
    for (const n of [next, prev]) if (n) loadDetail(route.runId, n.kind, n.id).catch(() => {});

    const conv = detail.replay || detail.baseline;
    const cid = route.id;
    const s = conv.structured || {};
    const notices = [];
    if (conv.evaluable && conv.evaluable.boundaries === false) notices.push(h('div', { class: 'notice' }, 'Boundaries unevaluable here' + (conv.evaluable.reason ? ': ' + conv.evaluable.reason : '') + '.'));
    if (detail.kind === 'production') notices.push(h('div', { class: 'notice info' }, 'Production had this conversation; the replay did not produce it. Everything below is production only.'));
    if ((detail.baselines || []).length > 1) notices.push(h('div', { class: 'notice info' }, 'The replay merged ' + detail.baselines.length + ' production conversations into this one: ' + detail.baselines.map((b) => clock(b.started_at) + ' ' + (b.title || 'untitled')).join(' · ') + '. Production below is those, joined.'));
    const siblings = detail.siblings || [];
    if (siblings.length) notices.push(h('div', { class: 'notice info' }, 'Same pairing group (' + (KIND_LABEL[(detail.group || {}).kind] || '') + '); the replay also made ', siblings.map((r, i) => [i ? ', ' : '', h('a', { href: convHref(route.runId, { kind: 'replay', id: r.id }) }, clock(r.started_at) + ' ' + (r.title || 'untitled'))]), '.'));
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
      homeBar(detail),
      h('div', { class: 'meta' },
        h('span', { class: 'item num' }, clock(conv.started_at) + '–' + clock(conv.finished_at) + ' · ' + dur((ms(conv.finished_at) - ms(conv.started_at)) / 1000)),
        conv.lane ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'lane'), conv.lane) : null,
        conv.language ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'lang'), conv.language) : null,
        conv.discarded ? h('span', { class: 'chip' }, 'discarded' + (conv.discard_reason ? ' · ' + conv.discard_reason.replace(/_/g, ' ') : '')) : null,
        detail.replay && detail.baseline && detail.baseline.discarded !== detail.replay.discarded ? h('span', { class: 'chip st-flipped' }, 'production ' + (detail.baseline.discarded ? 'discarded' : 'kept') + ' it') : null,
        detail.group ? h('span', { class: 'item' }, h('span', { class: 'label' }, 'what changed'), detail.group.change) : null,
        v3Meta(conv, detail)));

    const ctx = { runId: route.runId, cid, detail };
    return h('div', { class: 'page conv' }, header, notices,
      h('div', { class: 'conv-grid' }, leftColumn(ctx), rightColumn(ctx)));
  }

  /* Home state of both sides, side by side, at the top of the conversation page. */
  function homeBar(detail) {
    const hm = detail.home || {};
    const side = (label, rows, empty) => h('div', { class: 'hb-side' }, h('span', { class: 'label' }, label),
      rows && rows.length ? rows.map((x) => h('div', { class: 'hb-row' + (x.home ? ' home' : ' off') }, x.home ? h('span', { class: 'home-pill' }, 'HOME') : h('span', { class: 'hidden-note' }, 'hidden · ' + reasonWords(x.home_reason)),
        rows.length > 1 ? h('span', { class: 'hb-t' }, clock(x.started_at) + ' ' + (x.title || 'untitled')) : null)) : h('div', { class: 'hb-row none' }, empty));
    const flip = detail.group && (detail.group.tags || []).find((t) => t === 'home_dropped' || t === 'home_added');
    return h('div', { class: 'homebar' + (flip ? ' flip-' + (flip === 'home_dropped' ? 'drop' : 'add') : '') },
      side('Production', hm.production, 'not in production'),
      h('span', { class: 'hb-mid', title: detail.group ? KIND_TITLE[detail.group.kind] : '' }, detail.group ? detail.group.marker : ''),
      side('Replay', hm.replay ? [hm.replay] : [], 'not in replay'));
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

  /* Batch diarization abstains with a per-segment BATCH_UNASSIGNED_<segment>[_n] label: not a person. */
  const UNASSIGNED = /^BATCH_UNASSIGNED_/;
  function unassigned(seg) {
    return !seg.is_user && UNASSIGNED.test(seg.speaker_name || seg.speaker || '');
  }
  function speakerKey(seg) {
    if (seg.is_user) return '__user';
    return unassigned(seg) ? '__unassigned' : seg.speaker || seg.speaker_name || '?';
  }
  function speakerPalette(conv) {
    const map = new Map();
    for (const seg of (conv && conv.segments) || []) {
      const id = speakerKey(seg);
      if (!map.has(id)) map.set(id, seg.is_user ? 0 : (map.size % 5) + 1);
    }
    return map;
  }
  function speakerLabel(seg) {
    if (seg.is_user) return seg.speaker_name || 'You';
    if (unassigned(seg)) return 'Unassigned speaker';
    if (seg.speaker_name) return seg.speaker_name;
    const m = /(\d+)$/.exec(seg.speaker || '');
    return m ? 'Speaker ' + (+m[1]) : seg.speaker || 'Speaker';
  }

  function segmentRows(conv, audio, audioEl) {
    if (!conv || !(conv.segments || []).length) return [h('p', { class: 'empty' }, 'No transcript.')];
    const pal = speakerPalette(conv);
    const base = audio ? (ms(conv.started_at) - ms(audio.start)) / 1000 : 0;
    return conv.segments.map((seg) => {
      const idx = pal.get(speakerKey(seg));
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
        paras.push(h('div', { class: 'seg diffpara', style: '--sc:var(--spk-' + pal.get(speakerKey(seg)) + ')' }, h('div', { class: 'spk' }, speakerLabel(seg)), cur));
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
      summary: ((d.compare && d.compare.fields) || []).some((f) => f.class === 'substantive' && ['title', 'overview', 'events', 'home', 'boundary'].includes(f.field)),
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
      h('div', { class: 'item-top' }, h('span', { class: 'txt' }, h('span', { class: 'label' }, d.replay && d.baseline ? 'Every compared field' : 'Summary'), d.group ? h('span', { class: 'vsprod' }, '  · ' + d.group.change + ' (vs production)') : null), key ? verdictControls(target, verdictFor(target, d.verdicts)) : null),
      d.replay && d.baseline ? fieldTable(d) : null,
      h('details', { class: 'sum-more', open: !(d.replay && d.baseline) },
        h('summary', null, 'Full summaries side by side'),
        h('div', { class: 'summary-grid', style: 'margin-top:8px' }, replaySide, prodSide)));
    const cur = verdictFor(target, d.verdicts);
    if (cur && cur.note) item.append(h('div', { class: 'note-line' }, cur.note));
    if (key) vt(item, target, 'summary');
    pane.append(item);
    const events = ((r && r.events) || []).concat([]);
    if (events.length) pane.append(h('div', { class: 'item' }, h('span', { class: 'label' }, 'Events'), h('ul', null, events.map((e) => h('li', null, e.title || e.description || JSON.stringify(e))))));
    return pane;
  }

  const FIELD_LABEL = {
    home: 'On Home', home_reason: 'Hidden reason', discarded: 'Discarded', boundary: 'Time', title: 'Title', overview: 'Overview', emoji: 'Emoji',
    category: 'Category', events: 'Events', tasks: 'Tasks', memories: 'Memories', pushes: 'Pushes', transcript: 'Transcript',
  };
  function fieldValue(name, v) {
    if (v === null || v === undefined) return '—';
    if (name === 'home') return v ? 'HOME' : 'hidden';
    if (name === 'home_reason') return v ? reasonWords(v) : '—';
    if (name === 'discarded') return v ? 'yes' : 'no';
    if (name === 'boundary') return clock(v[0]) + '–' + clock(v[1]) + ' · ' + dur((ms(v[1]) - ms(v[0])) / 1000);
    if (name === 'transcript') return v + ' words';
    if (name === 'events' || name === 'tasks' || name === 'memories' || name === 'pushes') return String(v);
    return v === '' ? '(empty)' : String(v);
  }
  /* Every field the compare looked at, unchanged ones dimmed, so a "changed" is never invisible. */
  function fieldTable(d) {
    const rows = (d.compare && d.compare.fields) || [];
    const order = ['home', 'title', 'overview', 'emoji', 'category', 'events', 'tasks', 'memories', 'pushes', 'boundary', 'transcript', 'home_reason', 'discarded'];
    const sorted = rows.slice().sort((a, b) => order.indexOf(a.field) - order.indexOf(b.field));
    return h('table', { class: 'fields' },
      h('thead', null, h('tr', null, h('th', null, 'Field'), h('th', null, 'Replay'), h('th', null, 'Production'), h('th', null, ''))),
      h('tbody', null, sorted.map((f) => {
        const text = f.field === 'title' || f.field === 'overview';
        const changed = f.class !== 'same';
        const r = fieldValue(f.field, f.replay), p = fieldValue(f.field, f.production);
        return h('tr', { class: 'f-' + f.class },
          h('th', { scope: 'row' }, FIELD_LABEL[f.field] || f.field),
          h('td', { class: f.field === 'emoji' ? 'emo' : '' }, text && changed ? diffSide(p, r, 'new') : r),
          h('td', { class: f.field === 'emoji' ? 'emo' : '' }, text && changed ? diffSide(p, r, 'old') : p),
          h('td', { class: 'fc' }, f.class === 'same' ? 'same' : f.class === 'cosmetic' ? 'cosmetic' : fieldNote(f)));
      })));
  }
  function fieldNote(f) {
    const x = f.detail || {};
    if (x.what === 'rewritten') return 'rewritten';
    if (x.what === 'edited') return x.words_changed + ' word' + (x.words_changed === 1 ? '' : 's');
    if (x.what === 'added') return 'now on Home';
    if (x.what === 'dropped') return 'dropped off Home';
    if (x.added !== undefined) return ['+' + x.added, '−' + x.removed, x.edited ? x.edited + ' reworded' : null].filter(Boolean).join(' ');
    if (x.start_shift_s !== undefined) return 'edges moved';
    return 'differs';
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
        const href = verdictHref(v);
        return h('tr', { class: 'vrow', onclick: (e) => { if (!e.target.closest('a')) location.hash = href; } },
          h('td', null, h('span', { class: 'mark ' + v.mark }, v.mark === 'good' ? '👍 good' : '👎 bad')),
          h('td', null, (v.item_kind || '').replace('_', ' ')),
          h('td', { class: 'what' }, h('a', { href }, snapshotText(v.item_snapshot) || v.item_key), v.item_snapshot && v.item_snapshot.side === 'production' ? h('span', { class: 'vsprod' }, '  production side') : null),
          h('td', { class: 'note' }, v.note || ''),
          h('td', { class: 'runcol' }, h('code', null, v.ref || ''), h('div', { class: 'vsprod' }, v.run_id)),
          h('td', { class: 'when' }, v.at ? tz.format(new Date(v.at)) : ''));
      })))));
  }

  /* The server resolves where a verdict's item lives in its run (v.open); a production id is not a
     replay file in a v3 run, so the link must not be built from conversation_id. */
  function verdictHref(v) {
    const o = v.open;
    if (o && o.kind === 'replay') return '#/run/' + encodeURIComponent(o.run_id) + '/c/' + encodeURIComponent(o.id);
    if (o && o.kind === 'production') return '#/run/' + encodeURIComponent(o.run_id) + '/p/' + encodeURIComponent(o.id);
    return '#/run/' + encodeURIComponent(v.run_id);
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
        if (openSelection()) e.preventDefault();
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
