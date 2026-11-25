// Scenario run view: reads /api/run and /api/scenarios/<name>, nothing else. Builds the DOM with
// textContent only (no innerHTML), so scenario text is never parsed as markup.
'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  // zoom: null = the range that holds the Home moment shown; 'run' | 'events' once the reader picks one.
  const state = { overview: null, name: null, data: null, snap: null, card: null, side: null, zoom: null, repeat: 1 };
  const THEMES = ['auto', 'light', 'dark'];

  // ---- tiny DOM helper ------------------------------------------------------------------------
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'style') Object.assign(el.style, v);
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const child of children.flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }
  const missingNote = (file, where, what) =>
    h('p', { class: 'notice' }, h('b', { text: file }), ` is missing${where ? ' in ' + where : ''}: ${what}`);

  // ---- outcomes -------------------------------------------------------------------------------
  const OUTCOMES = {
    passed: { cls: 'pass', icon: '✓', text: 'Pass' },
    xfail: { cls: 'pass', icon: '✓', text: 'Pass', note: 'known bug, failing as expected' },
    failed: { cls: 'fail', icon: '✗', text: 'Fail' },
    nondeterministic: { cls: 'fail', icon: '≠', text: 'Nondeterministic', note: 'repeats of this scenario differ' },
    xpass: { cls: 'fail', icon: '✗', text: 'Fail', note: 'the known bug no longer fails: delete expected_failure' },
    error: { cls: 'error', icon: '!', text: 'Error' },
    unknown: { cls: 'unknown', icon: '?', text: 'No result' },
  };
  const outcomeOf = (o) => OUTCOMES[o] || OUTCOMES.unknown;
  const mark = (o, extra) => {
    const m = outcomeOf(o);
    return h('span', { class: `mark ${m.cls}` }, h('span', { 'aria-hidden': 'true', text: m.icon }), m.text + (extra || ''));
  };

  // ---- time -----------------------------------------------------------------------------------
  const secs = (t) => {
    if (t === null || t === undefined || Number.isNaN(t)) return '?';
    const sign = t < 0 ? '-' : '+';
    const a = Math.abs(t);
    if (a < 600) return `${sign}${Math.round(a * 10) / 10} s`;
    const m = Math.floor(a / 60), s = Math.round(a % 60);
    return `${sign}${m}:${String(s).padStart(2, '0')}`;
  };
  // One unit style per timeline axis: m:ss once the range exceeds 120 s, plain seconds below that.
  const axisFormat = (range) => (t) => {
    if (t === null || t === undefined || Number.isNaN(t)) return '?';
    const sign = t < 0 ? '-' : '';
    const a = Math.abs(t);
    if (range <= 120) return `${sign}${Math.round(a * 10) / 10} s`;
    const m = Math.floor(a / 60), s = Math.round(a % 60);
    return s === 60 ? `${sign}${m + 1}:00` : `${sign}${m}:${String(s).padStart(2, '0')}`;
  };
  // Underscores are the only places a scenario name may break.
  const breakable = (name) => String(name).split('_').flatMap((part, i, all) => (i < all.length - 1 ? [part + '_', h('wbr')] : [part]));

  // Transcript source per recording label: scripted (speech lines), synthetic, local or vendor (a cassette).
  const SOURCES = ['scripted', 'synthetic', 'local', 'vendor'];
  function sourcesOf(b) {
    const out = {};
    const s = b && b.scenario;
    for (const r of s ? [...(s.recordings || []), ...(s.sync || [])] : []) if (r && r.id) out[r.id] = r.audio_file ? '?' : 'scripted';
    const res = (b && b.result) || {};
    for (const r of (res.audio && res.audio.recordings) || []) if (r.label) out[r.label] = r.source || out[r.label];
    for (const r of res.recordings || []) if (r.label) out[r.label] = r.stt || out[r.label] || 'scripted';
    const v = b && b.verdict && b.verdict.transcripts;
    if (v && typeof v === 'object') Object.assign(out, v);
    return out;
  }
  const sourceTag = (src) => h('span', { class: 'src' + (src === 'scripted' ? '' : ' audio'), title: `transcript source: ${src}`, text: src });

  const t0Of = (b) => {
    const raw = b && b.scenario && b.scenario.t0;
    const d = new Date(raw || '2026-03-14T09:00:00Z');
    return Number.isNaN(d.getTime()) ? new Date('2026-03-14T09:00:00Z') : d;
  };
  const offsetOf = (b, iso) => {
    if (!iso) return null;
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? null : Math.round((d - t0Of(b)) / 100) / 10;
  };
  const clock = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '?' : d.toISOString().slice(11, 19);
  };

  // ---- model: recordings, conversations, Home -------------------------------------------------
  function labelOf(b, recId) {
    const s = b && b.scenario;
    const all = s ? [...(s.recordings || []), ...(s.sync || [])] : [];
    for (const r of all) if (r && typeof r.id === 'string' && 'scn-' + r.id.toLowerCase() === recId) return r.id;
    return String(recId || '?').replace(/^scn-/, '').toUpperCase();
  }

  // Recordings with their spans, from scenario.json; else approximated from the result timeline.
  function recordingsOf(b) {
    const s = b && b.scenario;
    const tl = (b && b.result && b.result.timeline) || [];
    const at = (kind, ref) => { const e = tl.find((x) => x.kind === kind && x.ref === ref); return e ? e.t : null; };
    if (s && Array.isArray(s.recordings)) {
      const out = [];
      for (const r of s.recordings) {
        const [a, z] = r.audio || [null, null];
        out.push({ label: r.id, origin: r.origin, lane: 'batch', start: a, end: z,
          sealed: r.sealed_at ?? z, landed: at('transcript', r.id) ?? r.transcript_at ?? null,
          provisional: at('admission', r.id), session: r.session });
      }
      for (const r of s.sync || []) {
        const [a, z] = r.audio || [null, null];
        out.push({ label: r.id, origin: r.origin, lane: 'sync', start: a, end: z, arrives: r.arrives_at ?? at('sync', r.id) });
      }
      return { recs: out, approx: false };
    }
    const byRef = {};
    for (const e of tl) {
      if (!e.ref || ['finish', 'reconcile'].includes(e.ref) || String(e.ref).startsWith('expect[')) continue;
      const r = (byRef[e.ref] = byRef[e.ref] || { label: e.ref, origin: '?', lane: 'batch' });
      if (e.kind === 'capture_start') r.start = e.t;
      if (e.kind === 'seal') { r.end = e.t; r.sealed = e.t; }
      if (e.kind === 'transcript') r.landed = e.t;
      if (e.kind === 'admission') r.provisional = e.t;
      if (e.kind === 'sync') { r.lane = 'sync'; r.arrives = e.t; r.start = e.t; r.end = e.t; }
    }
    return { recs: Object.values(byRef).filter((r) => r.start !== undefined), approx: true };
  }

  function snapshotsOf(b) {
    const snaps = (b && b.home && Array.isArray(b.home.snapshots)) ? b.home.snapshots : [];
    return snaps;
  }

  // The lab's conversation rows at a snapshot's moment (result.json), keyed by handle.
  function rowsAt(b, snap) {
    const r = (b && b.result) || {};
    let rows = r.conversations || [];
    if (snap && String(snap.label || '').startsWith('checkpoint@')) {
      const at = Number(String(snap.label).split('@')[1]);
      const seen = Object.values(r.checkpoints || {}).find((c) => Number(c.t) === at);
      if (seen) rows = seen.conversations || [];
    }
    return rows;
  }

  function cardsOf(b, snap) {
    if (!snap || snap.status !== 200 || !Array.isArray(snap.response)) return null;
    const rows = rowsAt(b, snap);
    const byHandle = Object.fromEntries(rows.map((r) => [r.handle, r]));
    const toCard = (raw, pos, live) => {
      const handle = String(raw.id || '').slice(0, 8);
      const row = byHandle[handle];
      const segs = Array.isArray(raw.transcript_segments) ? raw.transcript_segments : null;
      const words = row ? row.words : (segs ? segs.reduce((n, s) => n + String(s.text || '').split(/\s+/).filter(Boolean).length, 0) : null);
      const recs = row ? row.recordings : (raw.v3_recording_ids || []).map((id) => labelOf(b, id));
      const st = raw.structured || {};
      return { handle, id: raw.id, pos, live, raw, row, words,
        recordings: recs || [], title: st.title || '(no title)', emoji: st.emoji || '',
        start: raw.started_at, end: raw.finished_at, tile: raw.tile_state, kind: raw.kind };
    };
    const cards = snap.response.map((raw, i) => toCard(raw, i + 1, false));
    const live = snap.live && snap.live.status === 200 && snap.live.response && snap.live.response.conversation;
    if (live && !cards.some((c) => c.id === live.id)) cards.unshift(toCard(live, 0, true));
    return cards;
  }

  function hiddenOf(b, snap, cards) {
    const on = new Set((cards || []).map((c) => c.handle));
    return rowsAt(b, snap).filter((r) => !on.has(r.handle)).map((r) => ({
      row: r, handle: r.handle, recordings: r.recordings || [], words: r.words,
      reason: r.deleted ? 'deleted' : r.status === 'failed' ? 'failed' : (r.hidden_reason || (r.status === 'in_progress' ? 'in progress' : 'not returned by the Home route')),
      labVisible: !!r.visible,
    }));
  }

  // ---- loading --------------------------------------------------------------------------------
  async function getJSON(url) {
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `${res.status}`);
    return body;
  }

  function readHash() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [name, q] = raw.split('?');
    const p = new URLSearchParams(q || '');
    return { name: decodeURIComponent(name || ''), snap: p.get('snap'), card: p.get('card'), theme: p.get('theme'), zoom: p.get('zoom'), repeat: p.get('repeat') };
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.snap !== null) p.set('snap', state.snap);
    if (state.card) p.set('card', state.card);
    if (state.zoom) p.set('zoom', state.zoom);
    if (state.repeat > 1) p.set('repeat', String(state.repeat));
    const theme = document.documentElement.dataset.theme;
    if (theme) p.set('theme', theme);
    const q = p.toString();
    history.replaceState(null, '', `#/${encodeURIComponent(state.name || '')}${q ? '?' + q : ''}`);
  }

  async function boot() {
    const want = readHash();
    if (want.theme && THEMES.includes(want.theme)) setTheme(want.theme);
    if (want.zoom === 'events' || want.zoom === 'run') state.zoom = want.zoom;
    if (want.repeat && /^\d+$/.test(want.repeat)) state.repeat = Number(want.repeat);
    try {
      state.overview = await getJSON('/api/run');
    } catch (err) {
      $('main').replaceChildren(h('p', { class: 'empty', text: `Could not read the run directory: ${err.message}` }));
      return;
    }
    renderHeader();
    renderRail();
    const names = state.overview.scenarios || [];
    if (!names.length) {
      $('main').replaceChildren(h('p', { class: 'notice', text: `No scenario directories (with result.json, home.json or scenario.json) in ${state.overview.root}.` }));
      return;
    }
    await select(names.includes(want.name) ? want.name : names[0], want.snap, want.card, state.repeat);
  }

  async function select(name, snap, card, repeat) {
    let data;
    const k = repeat && repeat > 1 ? repeat : 1;
    try {
      data = await getJSON(`/api/scenarios/${encodeURIComponent(name)}${k > 1 ? '?repeat=' + k : ''}`);
    } catch (err) {
      $('main').replaceChildren(h('p', { class: 'empty', text: `Could not read scenario ${name}: ${err.message}` }));
      return;
    }
    if (state.name !== name) state.zoom = null;  // a new scenario starts on the range that holds its Home moment
    state.name = name;
    state.data = data;
    state.repeat = k;
    const primary = primaryBundle();
    const snaps = snapshotsOf(primary);
    state.snap = snap !== null && snap !== undefined && snaps[Number(snap)] ? Number(snap) : (snaps.length ? snaps.length - 1 : null);
    state.card = card || null;
    render();
    for (const btn of document.querySelectorAll('.rail-list button')) btn.setAttribute('aria-current', String(btn.dataset.name === name));
  }

  const isCompare = () => state.overview && state.overview.kind === 'compare';
  const primarySide = () => (isCompare() ? 'head' : 'run');
  const primaryBundle = () => (state.data && state.data.sides[primarySide()]) || null;

  // ---- header and rail ------------------------------------------------------------------------
  function runInfo(side) {
    const s = state.overview.sides[side] || {};
    const run = s.run || {};
    const pick = (...keys) => { for (const k of keys) if (run[k]) return run[k]; return null; };
    const tree = pick('backend_tree', 'tree', 'backend_tree_sha');
    const ref = pick('ref', 'head', 'sha', 'commit');
    const text = (v) => (v && typeof v === 'object' ? JSON.stringify(v) : v);
    return { ref: text(ref), tree: text(tree), run };
  }

  function renderHeader() {
    const o = state.overview;
    const meta = $('run-meta');
    meta.replaceChildren();
    const sides = isCompare() ? ['base', 'head'] : ['run'];
    for (const side of sides) {
      const info = runInfo(side);
      const prefix = isCompare() ? `${side} ` : '';
      if (info.ref || info.tree) {
        meta.append(h('span', { title: `${side}: ref ${info.ref || '?'}, backend tree ${info.tree || '?'}` }, prefix,
          info.ref ? h('b', { class: 'mono', text: String(info.ref).slice(0, isCompare() ? 28 : 48) }) : null,
          info.tree ? ` · tree ` : null, info.tree ? h('b', { class: 'mono', text: String(info.tree).slice(0, 10) }) : null));
      }
      if (!info.ref && !info.tree) meta.append(h('span', { text: `${prefix}${o.kind === 'scenario' ? 'one scenario directory' : 'run.json missing: no ref or tree'}` }));
    }
    const verdict = (o.sides[primarySide()] || {}).verdict;
    const outcomes = Object.values((o.sides[primarySide()] || {}).outcomes || {});
    const bad = outcomes.filter((x) => outcomeOf(x).cls !== 'pass').length;
    const v = $('run-verdict');
    const counts = h('span', { class: 'muted', text: `${outcomes.length - bad} of ${outcomes.length} scenarios pass ` });
    v.replaceChildren(counts,
      verdict && verdict.outcome ? mark(verdict.outcome, ' (verdict.json)') : mark(bad ? 'failed' : 'passed', bad ? ' run' : ' run'));
  }

  function renderRail() {
    const o = state.overview;
    const list = $('rail-list');
    list.replaceChildren();
    for (const name of o.scenarios) {
      const head = (o.sides[primarySide()] || {}).outcomes || {};
      const base = isCompare() ? ((o.sides.base || {}).outcomes || {})[name] : null;
      const btn = h('button', { type: 'button', 'data-name': name, 'aria-current': 'false', title: name, onclick: () => select(name) },
        mark(head[name] || 'unknown'),
        h('span', { class: 'rail-text' }, h('span', { class: 'rail-name' }, breakable(name)),
          isCompare() ? h('span', { class: 'rail-sub', text: `base: ${outcomeOf(base || 'unknown').text.toLowerCase()}` }) : null));
      list.append(h('li', {}, btn));
    }
    const notes = $('rail-notes');
    notes.replaceChildren();
    for (const [side, s] of Object.entries(o.sides)) {
      for (const m of s.missing || []) notes.append(h('p', { text: `${isCompare() ? side + '/' : ''}${m.file} ${m.problem}; marks come from each result.json.` }));
    }
    for (const m of o.missing || []) notes.append(h('p', { text: `${m.file} ${m.problem}; Home differences are computed from the two home.json files.` }));
    notes.append(h('p', { class: 'muted', text: o.root }));
  }

  // ---- main panel -----------------------------------------------------------------------------
  function render() {
    const b = primaryBundle();
    const main = $('main');
    const parts = [];
    if (!b) {
      parts.push(h('p', { class: 'notice', text: `This scenario is not in ${primarySide()}/.` }));
    } else {
      parts.push(verdictSection(b));
      parts.push(homeSection());
      parts.push(timelineSection(b));
      parts.push(standInSection(b));
    }
    main.replaceChildren(...parts);
    layoutLabels();
    syncSelection();
    writeHash();
  }

  function expectText(raw) {
    if (!raw) return null;
    if (raw.no_hidden_with) return `no hidden conversation holds ${raw.no_hidden_with}`;
    const fields = Object.entries(raw).filter(([k]) => !['at', 'label', 'conversation_of', 'no_hidden_with'].includes(k));
    const show = (v) => (Array.isArray(v) ? v.join(' + ') : v === true ? 'yes' : v === false ? 'no' : String(v));
    return `conversation of ${raw.conversation_of}: ` + fields.map(([k, v]) => `${k.replace(/_/g, ' ')} ${show(v)}`).join(' · ');
  }

  function verdictSection(b) {
    const r = b.result;
    const s = b.scenario;
    const sec = h('section', { class: 'section', 'aria-labelledby': 'v-title' });
    const outcome = (state.overview.sides[primarySide()].outcomes || {})[state.name] || (r && r.outcome) || 'unknown';
    const m = outcomeOf(outcome);
    sec.append(h('div', { class: 'verdict-head' },
      h('div', {}, h('h1', { id: 'v-title', text: state.name }),
        s ? h('p', { text: s.description || '(no description)' }) : h('p', { text: 'scenario.json is missing: no description.' })),
      h('div', { class: `big ${m.cls}`, role: 'status' }, h('span', { 'aria-hidden': 'true', text: m.icon }),
        h('span', {}, m.text, m.note ? h('small', { text: m.note }) : null))));
    if (isCompare()) {
      const base = state.data.sides.base;
      const bo = ((state.overview.sides.base || {}).outcomes || {})[state.name];
      sec.append(h('p', { class: 'meta-line' }, 'base: ', base ? mark(bo || 'unknown') : 'not in base/', '  head: ', mark(outcome)));
    }
    const repeats = b.repeats || [];
    if (repeats.length > 1) {
      const pick = h('div', { class: 'snap-pick', role: 'group', 'aria-label': 'Repeat shown' });
      for (const rp of repeats) {
        pick.append(h('button', { type: 'button', 'aria-pressed': String(rp.repeat === (b.repeat || 1)),
          onclick: () => select(state.name, null, null, rp.repeat) }, mark(rp.outcome, ` · repeat ${rp.repeat}`)));
      }
      sec.append(h('p', { class: 'meta-line', text: `Ran ${repeats.length} times (--repeat ${repeats.length}); repeat 1 is ${state.name}/, repeat k is ${state.name}/repeat-k/.` }), pick);
    }
    const vrow = b.verdict;
    if (vrow && vrow.outcome === 'nondeterministic') {
      const diffs = vrow.differences || [];
      sec.append(h('div', { class: 'notice nondet' }, h('b', { text: '≠ Nondeterministic: ' }),
        `the repeats disagree after dropping wall-clock fields (determinism.SCENARIO_ARTIFACTS) at ${diffs.length} place${diffs.length === 1 ? '' : 's'}:`,
        h('ul', { class: 'mono' }, diffs.slice(0, 20).map((d) => h('li', { text: d }))),
        diffs.length > 20 ? h('p', { text: `and ${diffs.length - 20} more (verdict.json).` }) : null));
    }
    if (!r) {
      sec.append(missingNote('result.json', b.dir, 'no checks to show.'));
      return sec;
    }
    if (r.error) sec.append(h('p', { class: 'notice' }, h('b', { text: 'Error: ' }), String(r.error), r.log ? ` (log: ${r.log})` : ''));
    const failure = r.expected_failure;
    if (failure) sec.append(h('p', { class: 'meta-line', text: `Known bug: ${failure.reason} (checks: ${(failure.checks || []).join(', ')})` }));
    const expects = (s && s.expect) || [];
    const rows = (r.checks || []).map((c, i) => ({ c, i, raw: expects[i] }));
    rows.sort((x, y) => Number(x.c.ok) - Number(y.c.ok) || x.i - y.i);
    if (rows.length) {
      const table = h('table', { class: 'checks' },
        h('colgroup', {}, h('col', { class: 'c-res' }), h('col', { class: 'c-label' }), h('col'), h('col')),
        h('thead', {}, h('tr', {}, h('th', { text: 'Result' }), h('th', { text: 'Check' }), h('th', { text: 'Expected' }), h('th', { text: 'Actual' }))));
      const body = h('tbody');
      for (const { c, i, raw } of rows) {
        // The check's own label; else its summary (never a bare "check N").
        const summary = String(c.check || '').replace(/^\[[^\]]+\]\s*/, '').replace(/^@\+[\d.]+s\s*/, '');
        const label = (raw && raw.label) || (String(c.check).match(/^\[([^\]]+)\]/) || [])[1] || summary || `check ${i + 1}`;
        const when = raw ? (raw.at !== undefined && raw.at !== null ? `at ${secs(raw.at)}` : 'end of run') : (String(c.check).match(/@\+([\d.]+)s/) ? `at +${String(c.check).match(/@\+([\d.]+)s/)[1]} s` : 'end of run');
        const expected = expectText(raw) || String(c.check).replace(/^\[[^\]]+\]\s*/, '').replace(/^@\+[\d.]+s\s*/, '');
        body.append(h('tr', { class: c.ok ? 'ok' : 'bad' },
          h('td', {}, mark(c.ok ? 'passed' : 'failed')),
          h('td', {}, label, h('span', { class: 'when', text: when })),
          h('td', { text: expected }),
          h('td', { class: 'mono', text: c.detail })));
      }
      table.append(body);
      sec.append(table);
    } else {
      sec.append(h('p', { class: 'notice', text: 'This run has no checks.' }));
    }
    const sources = sourcesOf(b);
    if (Object.keys(sources).length) {
      sec.append(h('p', { class: 'meta-line' }, 'Transcripts: ',
        Object.entries(sources).map(([label, src], i) => [i ? ' · ' : '', h('span', { class: 'chip' }, label, ' ', sourceTag(src))])));
    }
    if (r.finish_target !== undefined) sec.append(h('p', { class: 'meta-line', text: `Finish ended recording: ${r.finish_target ?? 'none'} · ran in ${r.seconds ?? '?'} s` }));
    return sec;
  }

  // ---- Home -----------------------------------------------------------------------------------
  function snapLabel(snap) {
    if (!snap) return '?';
    return snap.label === 'final' ? `End of run (${secs(snap.at)})` : `Checkpoint ${secs(Number(String(snap.label).split('@')[1]))}`;
  }

  function homeSection() {
    const b = primaryBundle();
    const sec = h('section', { class: 'section', 'aria-labelledby': 'h-title' });
    sec.append(h('h2', { id: 'h-title' }, 'Home', h('span', { class: 'hint', text: 'what the product’s Home route returned, in its order' })));
    sec.append(h('p', { class: 'home-note', text: 'This is what the server returned. The phone also hides some rows itself (short conversations, failed tiles, rows marked hidden); that filter is not modelled here.' }));
    const snaps = snapshotsOf(b);
    if (!b.home) {
      sec.append(missingNote('home.json', b.dir, 'Home cannot be shown. The lab’s own visibility rule is in the timeline below.'));
      return sec;
    }
    if (!snaps.length) { sec.append(h('p', { class: 'notice', text: 'home.json has no snapshots.' })); return sec; }
    const pick = h('div', { class: 'snap-pick', role: 'group', 'aria-label': 'Moment shown' });
    snaps.forEach((snap, i) => pick.append(h('button', { type: 'button', 'aria-pressed': String(i === state.snap),
      onclick: () => { state.snap = i; render(); } }, snapLabel(snap))));
    sec.append(pick);
    const cols = h('div', { class: 'home-cols' });
    if (isCompare()) {
      const base = state.data.sides.base;
      const headSnap = snaps[state.snap];
      const baseSnaps = snapshotsOf(base);
      const baseSnap = baseSnaps.find((s) => s.label === headSnap.label) || baseSnaps[baseSnaps.length - 1];
      const diff = compareCards(cardsOf(base, baseSnap), cardsOf(b, headSnap));
      cols.append(phone('base', base, baseSnap, diff.base), phone('head', b, headSnap, diff.head));
      sec.append(cols);
      sec.append(compareSummary(diff));
    } else {
      cols.append(phone(null, b, snaps[state.snap], null));
      sec.append(cols);
    }
    const dis = (b.home.disagreements || []);
    if (dis.length) {
      sec.append(h('p', { class: 'disagree' }, h('span', { 'aria-hidden': 'true', text: '⚠ ' }),
        `The lab’s own rule disagrees with the route ${dis.length} time(s): ` +
        dis.map((d) => `${d.label} ${d.recordings.join('+')} lab ${d.lab_visible ? 'visible' : 'hidden'}, route ${d.on_home ? 'on Home' : 'not on Home'}`).join('; ')));
    }
    return sec;
  }

  function phone(side, b, snap, diffs) {
    const col = h('div', { class: 'phone', 'aria-label': side ? `Home (${side})` : 'Home' });
    if (!b) { col.append(h('p', { class: 'notice', text: `Not in ${side}/.` })); return col; }
    if (!b.home) { col.append(missingNote('home.json', b.dir, 'Home cannot be shown.')); return col; }
    const cards = cardsOf(b, snap);
    col.append(h('div', { class: 'phone-head' }, h('b', { text: side ? `Home · ${side}` : 'Home' }),
      h('span', { text: snap ? `${snapLabel(snap)} · HTTP ${snap.status}` : '' })));
    col.append(h('div', { class: 'route-line mono', text: `${b.home.route || '?'} · ${b.home.evidence || ''}` }));
    if (cards === null) {
      col.append(h('p', { class: 'notice', text: `The route did not answer 200 at this moment${snap && snap.error ? ': ' + snap.error : ''}.` }));
      return col;
    }
    const list = h('ul', { class: 'cards', 'aria-label': 'Home cards in route order' });
    if (!cards.length) list.append(h('li', {}, h('p', { class: 'muted', text: 'Home is empty.' })));
    for (const card of cards) {
      const d = diffs ? diffs.get(card.handle) : null;
      list.append(h('li', {}, cardButton(b, card, side, d)));
    }
    col.append(list);
    const hidden = hiddenOf(b, snap, cards);
    const det = h('details', { class: 'hidden-group' }, h('summary', { text: `Not on Home (${hidden.length})` }));
    const ul = h('ul');
    if (!b.result) ul.append(h('li', {}, missingNote('result.json', b.dir, 'the hidden conversations are not known.')));
    for (const x of hidden) {
      const key = x.handle;
      ul.append(h('li', {}, h('button', { type: 'button', class: 'card', 'data-card': key, 'data-side': side || '', 'aria-pressed': 'false',
        onclick: () => openCard(key, side) },
        h('div', { class: 'card-title' }, h('span', { class: 'mono', text: x.handle }), h('span', { text: x.recordings.join(' + ') || '(no recordings)' })),
        h('div', { class: 'card-meta', text: `${x.words ?? '?'} words` }),
        h('div', { class: 'reason' }, h('span', { 'aria-hidden': 'true', text: '⦸ ' }), `Hidden: ${x.reason}`),
        x.labVisible ? h('div', { class: 'disagree', text: '⚠ the lab’s own rule says visible' }) : null)));
    }
    det.append(ul);
    col.append(det);
    return col;
  }

  function cardButton(b, card, side, diff) {
    const span = `${clock(card.start)}–${clock(card.end)} (${secs(offsetOf(b, card.start))} to ${secs(offsetOf(b, card.end))})`;
    const btn = h('button', { type: 'button', class: 'card' + (diff && diff.kind !== 'same' ? ' differs' : ''), 'data-card': card.handle,
      'data-side': side || '', 'aria-pressed': 'false', onclick: () => openCard(card.handle, side) },
      h('div', { class: 'card-title' }, h('span', { class: 'pos', text: card.live ? 'live' : `${card.pos}.` }),
        h('span', { text: `${card.emoji ? card.emoji + ' ' : ''}${card.title}` })),
      h('div', { class: 'card-meta', text: `${span} · ${card.words ?? '?'} words` }),
      h('div', { class: 'chips' },
        card.recordings.map((r) => h('span', { class: 'chip' }, r, ' ', sourceTag(sourcesOf(b)[r] || 'scripted'))),
        card.live ? h('span', { class: 'chip live', text: 'in progress (live route)' }) : null,
        card.row && !card.row.visible ? h('span', { class: 'chip diff', text: '⚠ lab rule: hidden' }) : null,
        diff && diff.kind === 'only' ? h('span', { class: 'chip diff', text: `only in ${side}` }) : null,
        diff && diff.kind === 'changed' ? h('span', { class: 'chip diff', text: `differs: ${diff.fields.join(', ')}` }) : null));
    return btn;
  }

  // ---- compare --------------------------------------------------------------------------------
  function compareCards(baseCards, headCards) {
    const out = { base: new Map(), head: new Map(), rows: [] };
    if (!baseCards || !headCards) return out;
    const key = (c) => [...c.recordings].sort().join('+');
    const used = new Set();
    const fields = (a, z) => {
      const f = [];
      if (a.title !== z.title) f.push('title');
      if (a.start !== z.start || a.end !== z.end) f.push('time');
      if (a.words !== z.words) f.push('words');
      if (key(a) !== key(z)) f.push('recordings');
      if (a.pos !== z.pos) f.push('position');
      if (a.tile !== z.tile) f.push('tile state');
      return f;
    };
    for (const z of headCards) {
      const a = baseCards.find((c) => !used.has(c) && c.id === z.id) || baseCards.find((c) => !used.has(c) && key(c) === key(z));
      if (!a) { out.head.set(z.handle, { kind: 'only' }); out.rows.push({ head: z }); continue; }
      used.add(a);
      const f = fields(a, z);
      const d = { kind: f.length ? 'changed' : 'same', fields: f };
      out.head.set(z.handle, d); out.base.set(a.handle, d); out.rows.push({ base: a, head: z, fields: f });
    }
    for (const a of baseCards) if (!used.has(a)) { out.base.set(a.handle, { kind: 'only' }); out.rows.push({ base: a }); }
    return out;
  }

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const cardName = (c) => (c.recordings.length ? c.recordings.join('+') : c.handle) + (c.title ? ` (“${c.title}”)` : '');
  const valueText = (v) => (v === null || v === undefined ? '-' : Array.isArray(v) ? v.join('+') : v === true ? 'yes' : v === false ? 'no' : String(v));

  // Plain sentences: the cards at this moment (from the two home.json files), then compare.json's final state.
  function compareSummary(diff) {
    const box = h('div', { class: 'compare-summary' });
    const changed = diff.rows.filter((r) => !r.base || !r.head || (r.fields && r.fields.length));
    if (!changed.length) {
      box.append(h('p', { text: 'Base and head agree.' }));
    } else {
      const fields = [...new Set(changed.flatMap((r) => (r.base && r.head ? r.fields : ['present'])))];
      const named = fields.map((f) => (f === 'present' ? 'on one side only' : f));
      box.append(h('p', { text: `${plural(changed.length, 'card differs', 'cards differ')}: ${named.join(', ')}.` }));
      const ul = h('ul');
      for (const row of changed) {
        if (!row.base) ul.append(h('li', { text: `${cardName(row.head)}: only in head.` }));
        else if (!row.head) ul.append(h('li', { text: `${cardName(row.base)}: only in base.` }));
        else {
          const what = row.fields.map((f) => {
            const pick = { title: 'title', words: 'words', 'tile state': 'tile' }[f];
            return pick ? `${f} ${valueText(row.base[pick])} → ${valueText(row.head[pick])}` : f;
          });
          ul.append(h('li', { text: `${cardName(row.head)}: ${what.join('; ')}.` }));
        }
      }
      box.append(ul);
    }
    const cmp = state.overview.compare;
    const entry = cmp && Array.isArray(cmp.scenarios) ? cmp.scenarios.find((x) => x && x.name === state.name) : null;
    if (entry) {
      const lines = [];
      if (entry.base !== entry.head) lines.push(`The outcome differs: base ${outcomeOf(entry.base).text.toLowerCase()}, head ${outcomeOf(entry.head).text.toLowerCase()}.`);
      const convs = entry.conversations || [];
      if (!entry.differs) lines.push('At the end of the run, base and head agree on every conversation (compare.json).');
      else if (convs.length) lines.push(`At the end of the run, ${plural(convs.length, 'conversation differs', 'conversations differ')} (compare.json):`);
      box.append(...lines.map((t) => h('p', { text: t })));
      if (convs.length) {
        box.append(h('ul', {}, convs.map((c) => {
          if (!c.base) return h('li', { text: `${c.key}: only in head.` });
          if (!c.head) return h('li', { text: `${c.key}: only in base.` });
          return h('li', { text: `${c.key}: ${c.fields.map((f) => `${f.replace(/_/g, ' ')} ${valueText(c.base[f])} → ${valueText(c.head[f])}`).join('; ')}.` });
        })));
      }
    } else if (isCompare() && !cmp) {
      box.append(missingNote('compare.json', state.overview.root, 'the sentence above is computed in the page from the two home.json files.'));
    }
    return box;
  }

  // ---- timeline -------------------------------------------------------------------------------
  function niceStep(span) {
    const target = span / 8;
    for (const s of [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]) if (s >= target) return s;
    return 3600;
  }

  function timelineSection(b) {
    const sec = h('section', { class: 'section', 'aria-labelledby': 't-title' });
    const r = b.result;
    if (!r) {
      sec.append(h('h2', { id: 't-title' }, 'Timeline'));
      sec.append(missingNote('result.json', b.dir, 'no timeline to show.'));
      return sec;
    }
    const { recs, approx } = recordingsOf(b);
    const sources = sourcesOf(b);
    const tl = r.timeline || [];
    const snaps = snapshotsOf(b);
    const snap = snaps[state.snap];
    const convRows = rowsAt(b, snap);
    const cards = cardsOf(b, snap);
    const onHome = new Set((cards || []).map((c) => c.handle));
    const finite = (arr) => arr.filter((t) => typeof t === 'number' && Number.isFinite(t));
    const times = finite([0, ...tl.map((e) => e.t), ...recs.flatMap((x) => [x.start, x.end, x.landed, x.arrives]), ...snaps.map((s) => s.at)]);
    // The scripted events (captures, taps, landings, checks), without the reconcile and sweep tail.
    const eventTimes = finite([0, ...tl.filter((e) => !['task', 'sweep'].includes(e.kind)).map((e) => e.t),
      ...recs.flatMap((x) => [x.start, x.end, x.landed, x.arrives])]);
    const lo = Math.min(...times), runEnd = Math.max(...times), eventsEnd = Math.max(...eventTimes);
    const zoomable = eventsEnd < runEnd * 0.6;
    // Default: the range that holds the Home moment shown (the smaller one when both do).
    const auto = zoomable && snap && snap.at <= eventsEnd ? 'events' : 'run';
    const zoom = zoomable ? (state.zoom || auto) : 'run';
    const hi = zoom === 'events' ? eventsEnd : runEnd;
    const span = Math.max(1, hi - lo) * 1.03;
    const fmt = axisFormat(hi - lo);
    sec.append(h('h2', { id: 't-title' }, 'Timeline', h('span', { class: 'hint', text: `${hi - lo > 120 ? 'm:ss' : 'seconds'} from t0; select a Home card to highlight its recordings` })));
    if (approx) sec.append(missingNote('scenario.json', b.dir, 'recording spans are approximated from the timeline events (first audio to seal).'));
    if (zoomable) {
      const pick = h('div', { class: 'snap-pick', role: 'group', 'aria-label': 'Timeline range' });
      for (const [k, label] of [['run', `Whole run (to ${fmt(runEnd)})`], ['events', `Scripted events (to ${axisFormat(eventsEnd - lo)(eventsEnd)})`]]) {
        pick.append(h('button', { type: 'button', 'aria-pressed': String(zoom === k), onclick: () => { state.zoom = k; render(); } }, label));
      }
      sec.append(pick);
    }
    const pct = (t) => ((Math.min(t, hi + span * 0.02) - lo) / span) * 100;
    const x = (t) => `${pct(t)}%`;
    const w = (a, z) => `${Math.max(0, pct(z) - pct(a))}%`;
    // A text label for a point in time. Labels are laid out after render (layoutLabels): beside their
    // marker when there is room, else stacked on a row below with a leader line; the marker never moves.
    const label = (t, text, cls, title) => h('span', { class: 'lbl' + (cls ? ' ' + cls : ''), 'data-pct': String(pct(t)), title, text });
    // A bar too narrow for its text gets the text as a label instead.
    const bar = (cls, a, z, text, attrs) => {
      const narrow = pct(z) - pct(a) < 7;
      const el = h('span', { class: cls, style: { left: x(a), width: w(a, z) }, ...attrs, text: narrow ? '' : text });
      return narrow ? [el, label(z, text, 'beside', attrs && attrs.title)] : [el];
    };
    const box = h('div', { class: 'tl' + (state.card ? ' has-sel' : ''), id: 'timeline' });

    // axis
    const axis = h('div', { class: 'tl-track' });
    const step = niceStep(span);
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) axis.append(h('span', { class: 'tick', style: { left: x(t) }, text: fmt(t) }));
    box.append(h('div', { class: 'tl-row tl-axis' }, h('span', { class: 'tl-label', text: 't0 = ' + clock(t0Of(b).toISOString()) }), axis));

    // markers row: Finish tap, checkpoints, the moment shown
    const marks = h('div', { class: 'tl-track' });
    const finish = tl.find((e) => e.kind === 'finish');
    const checkpoints = tl.filter((e) => e.kind === 'checkpoint');
    const overlay = [];
    const inRange = (t) => t <= hi;
    if (finish && inRange(finish.t)) {
      overlay.push(['finish', finish.t]);
      marks.append(h('span', { class: 'pin mk finish', style: { left: x(finish.t) }, 'aria-hidden': 'true', text: '▼' }), label(finish.t, `Finish ${fmt(finish.t)}`, 'finish'));
    }
    const seenCheck = new Set();
    for (const c of checkpoints.filter((e) => inRange(e.t))) {
      overlay.push(['check', c.t]);
      if (seenCheck.has(c.t)) continue;  // two checks at one instant: one marker
      seenCheck.add(c.t);
      marks.append(h('span', { class: 'pin mk', style: { left: x(c.t) }, 'aria-hidden': 'true', text: '◆' }), label(c.t, `check ${fmt(c.t)}`));
    }
    if (snap) overlay.push(['snap', snap.at]);
    box.append(h('div', { class: 'tl-row' }, h('span', { class: 'tl-label', text: 'Taps, checks' }), marks));

    // one row per origin
    const origins = [...new Set(recs.map((rec) => rec.origin))];
    const gaps = (b.scenario && b.scenario.gaps) || [];
    for (const origin of origins) {
      const track = h('div', { class: 'tl-track' });
      for (const g of gaps.filter((g) => g.origin === origin)) {
        const [a, z] = (g.between || []).map((l) => recs.find((rec) => rec.label === l));
        if (a && z && a.end !== undefined && z.start !== undefined) {
          track.append(h('span', { class: 'span gapzone', style: { left: x(a.end), width: w(a.end, z.start) }, title: `stream gap (${g.reason || 'reconnect'}) ${Math.round(z.start - a.end)} s`, text: `gap ${Math.round(z.start - a.end)} s` }));
        }
      }
      for (const rec of recs.filter((q) => q.origin === origin)) {
        const sync = rec.lane === 'sync';
        const src = sources[rec.label] || 'scripted';
        if (rec.start !== undefined && rec.end !== undefined) {
          track.append(...bar('span rec' + (sync ? ' sync' : ''), rec.start, rec.end, `${rec.label} · ${src}`,
            { 'data-rec': rec.label, title: `${rec.label}: audio ${fmt(rec.start)} to ${fmt(rec.end)}${sync ? ', device sync' : ''}, transcript ${src}` }));
        }
        if (!sync && typeof rec.sealed === 'number' && inRange(rec.sealed)) track.append(h('span', { class: 'pin seal', style: { left: x(rec.sealed) }, title: `${rec.label} sealed ${fmt(rec.sealed)}`, text: '┃' }));
        if (!sync && typeof rec.provisional === 'number' && (r.fast_finish || {})[rec.label] && inRange(rec.provisional)) track.append(h('span', { class: 'pin landed', style: { left: x(rec.provisional) }, title: `${rec.label} fast-finish provisional transcript ${fmt(rec.provisional)} (${r.fast_finish[rec.label]})`, text: '◐' }));
        if (!sync && typeof rec.landed === 'number' && inRange(rec.landed)) {
          const title = `${rec.label} batch transcript landed ${fmt(rec.landed)}`;
          track.append(h('span', { class: 'pin landed', style: { left: x(rec.landed) }, title, text: '●' }), label(rec.landed, rec.label, 'landed', title));
        }
        if (sync && typeof rec.arrives === 'number' && inRange(rec.arrives)) {
          const title = `${rec.label} sync fragment arrived ${fmt(rec.arrives)}`;
          track.append(h('span', { class: 'pin arrive', style: { left: x(rec.arrives) }, title, text: '↓' }), label(rec.arrives, rec.label, 'arrive', title));
        }
      }
      box.append(h('div', { class: 'tl-row' }, h('span', { class: 'tl-label', title: `origin ${origin}`, text: `Origin ${origin}` }), track));
    }

    // one bar per conversation at the moment shown
    const byLabel = Object.fromEntries(recs.map((rec) => [rec.label, rec]));
    const live = convRows.filter((c) => !c.deleted);
    if (!live.length) box.append(h('div', { class: 'tl-row' }, h('span', { class: 'tl-label', text: 'Conversations' }), h('span', { class: 'muted', text: 'none at this moment' })));
    for (const c of live) {
      const spans = (c.recordings || []).map((l) => byLabel[l]).filter(Boolean);
      const a = Math.min(...spans.map((q) => q.start)), z = Math.max(...spans.map((q) => q.end));
      const shown = cards ? onHome.has(c.handle) : !!c.visible;
      const track = h('div', { class: 'tl-track' });
      if (spans.length && Number.isFinite(a) && Number.isFinite(z)) {
        track.append(...bar('span conv' + (shown ? '' : ' off'), a, Math.max(z, a + span * 0.01),
          `${shown ? '■' : '□'} ${(c.recordings || []).join('+')} · ${c.words} w · ${shown ? 'on Home' : 'not on Home'}`,
          { 'data-conv': c.handle, title: `${c.handle}: ${(c.recordings || []).join(' + ')}, ${shown ? 'on Home' : 'not on Home'}` }));
      }
      box.append(h('div', { class: 'tl-row' }, h('span', { class: 'tl-label mono', text: c.handle }), track));
    }
    // vertical lines across the rows (after the rows exist)
    const tracksLeft = 96;
    const lines = h('div', { style: { position: 'absolute', left: tracksLeft + 'px', right: '0', top: '22px', bottom: '0', pointerEvents: 'none' } });
    if (snap && snap.at > hi) sec.append(h('p', { class: 'meta-line', text: `The moment shown in Home (${fmt(snap.at)}) is past the end of this range.` }));
    for (const [kind, t] of overlay.filter(([, t]) => t <= hi)) lines.append(h('span', { class: `vline ${kind}`, style: { left: x(t) }, title: kind }));
    box.append(lines);
    sec.append(box);
    sec.append(h('div', { class: 'legend' },
      h('span', {}, h('span', { class: 'sw rec' }), 'audio (batch)'), h('span', {}, h('span', { class: 'sw sync' }), 'device-sync fragment'),
      h('span', {}, h('i', { text: '┃' }), ' seal'), h('span', {}, h('i', { text: '◐' }), ' fast-finish provisional transcript'), h('span', {}, h('i', { text: '●' }), ' batch transcript landed'),
      h('span', {}, h('i', { text: '↓' }), ' sync arrival'), h('span', {}, h('span', { class: 'sw gap' }), 'stream gap'),
      h('span', {}, h('span', { class: 'sw on' }), 'conversation on Home'), h('span', {}, h('span', { class: 'sw off' }), 'not on Home'),
      h('span', {}, h('i', { text: '▼' }), ' Finish tap'), h('span', {}, h('i', { text: '◆' }), ' checkpoint'),
      h('span', {}, h('i', { style: { color: 'var(--warn)' }, text: '│' }), ' moment shown in Home')),
      h('div', { class: 'legend' }, h('span', {}, 'Transcript source of each recording: ', SOURCES.map((x, i) => [i ? ' ' : '', sourceTag(x)]),
        ' (speech lines in the scenario; or an STT cassette for its audio file: the committed synthetic fixture, a local model, a vendor)')));
    return sec;
  }

  // Place each track's labels (.lbl) without overlap: beside the marker on the first row that has room,
  // rows below the track's bars getting a leader line back to the marker's true position.
  const ROW = 14, FIRST = 9, BELOW = 30;
  function layoutLabels() {
    const tl = $('timeline');
    if (!tl) return;
    for (const track of tl.querySelectorAll('.tl-track')) {
      for (const old of track.querySelectorAll('.leader')) old.remove();
      const labels = [...track.querySelectorAll('.lbl')];
      if (!labels.length) continue;
      const width = track.clientWidth;
      const placed = labels.map((el) => ({ el, at: (Number(el.dataset.pct) / 100) * width, w: el.offsetWidth }))
        .sort((p, q) => p.at - q.at);
      // Things already on row 0 that a label must not cover: bars' text and the point glyphs (.pin, which
      // are centred on their instant by a transform that offsetLeft does not include).
      const taken = [[]];
      for (const el of track.querySelectorAll('.span, .pin')) {
        if (!el.textContent) continue;
        const half = el.classList.contains('pin') && !el.classList.contains('side') ? el.offsetWidth / 2 : 0;
        taken[0].push([el.offsetLeft - half, el.offsetLeft - half + el.offsetWidth]);
      }
      const fits = (row, a, z) => !(taken[row] || []).some(([p, q]) => a < q + 2 && z > p - 2);
      let rows = 0;
      for (const p of placed) {
        let a = p.at + 7, z = a + p.w;
        if (z > width) { z = p.at - 7; a = z - p.w; }  // no room on the right: put it on the left of the marker
        let row = 0;
        while (!fits(row, a, z)) row += 1;
        (taken[row] = taken[row] || []).push([a, z]);
        rows = Math.max(rows, row);
        const top = row === 0 ? FIRST : BELOW + (row - 1) * ROW;
        Object.assign(p.el.style, { left: `${a}px`, top: `${top}px` });
        if (row > 0) {
          track.append(h('span', { class: 'leader', style: { left: `${p.at}px`, top: `${FIRST + 12}px`, height: `${top - FIRST - 4}px` } }));
        }
      }
      track.style.height = rows ? `${BELOW + rows * ROW + 2}px` : '';
    }
  }
  window.addEventListener('resize', () => requestAnimationFrame(layoutLabels));

  // ---- stand-ins ------------------------------------------------------------------------------
  // The lines are written per run by scenario/standins.py from the run's own counters (result.json
  // stand_in_notes, audio_steps); an older run directory without them shows its counts only.
  function standInSection(b) {
    const sec = h('section', { class: 'section', 'aria-labelledby': 's-title' });
    sec.append(h('h2', { id: 's-title' }, 'Stand-ins', h('span', { class: 'hint', text: 'steps that ran as lab stand-ins instead of product code in this run' })));
    const r = b.result;
    if (!r) { sec.append(missingNote('result.json', b.dir, 'the stand-in counts are not known.')); return sec; }
    const ul = h('ul', { class: 'standins' });
    const notes = r.stand_in_notes;
    if (Array.isArray(notes)) {
      for (const n of notes) ul.append(h('li', {}, h('b', { class: 'mono', text: n.count ? `${n.name} ×${n.count}` : n.name }), ' ', n.text || ''));
    } else {
      for (const [k, n] of Object.entries(r.stand_ins || {})) ul.append(h('li', {}, h('b', { class: 'mono', text: `${k} ×${n}` }), ' ', h('span', { class: 'muted', text: '(this run predates per-run stand-in notes)' })));
    }
    for (const a of r.audio_steps || []) ul.append(h('li', {}, h('b', { text: 'audio to words' }), ' ', a.text || ''));
    if (!Object.keys(r.stand_ins || {}).length) sec.append(h('p', { class: 'muted', text: 'No counted stand-in ran.' }));
    sec.append(ul);
    return sec;
  }

  // ---- selection and drawer -------------------------------------------------------------------
  function findCard(handle, side) {
    const b = side === 'base' ? state.data.sides.base : primaryBundle();
    if (!b) return null;
    const snaps = snapshotsOf(b);
    let snap = snaps[state.snap];
    if (side === 'base') {
      const head = snapshotsOf(primaryBundle())[state.snap];
      snap = snaps.find((s) => head && s.label === head.label) || snaps[snaps.length - 1];
    }
    const cards = cardsOf(b, snap) || [];
    const card = cards.find((c) => c.handle === handle);
    if (card) return { b, card };
    const hidden = hiddenOf(b, snap, cards).find((x) => x.handle === handle);
    return hidden ? { b, hidden } : null;
  }

  function openCard(handle, side) {
    state.card = handle;
    state.side = side || null;
    syncSelection();
    writeHash();
  }

  function closeDrawer() {
    const had = state.card;
    state.card = null;
    syncSelection();
    writeHash();
    if (had) { const btn = document.querySelector(`[data-card="${CSS.escape(had)}"]`); if (btn) btn.focus(); }
  }

  function syncSelection() {
    const found = state.card ? findCard(state.card, state.side) : null;
    const recs = new Set(found ? (found.card ? found.card.recordings : found.hidden.recordings) : []);
    for (const el of document.querySelectorAll('[data-card]')) {
      const on = !!found && el.dataset.card === state.card;
      el.setAttribute('aria-pressed', String(on));
      const group = on && el.closest('details');
      if (group) group.open = true;
    }
    const tl = $('timeline');
    if (tl) {
      tl.classList.toggle('has-sel', !!found);
      for (const el of tl.querySelectorAll('[data-rec]')) el.classList.toggle('sel', recs.has(el.dataset.rec));
      for (const el of tl.querySelectorAll('[data-conv]')) el.classList.toggle('sel', !!found && el.dataset.conv === state.card);
    }
    const drawer = $('drawer');
    if (!found) { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); return; }
    fillDrawer(found);
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function fillDrawer({ b, card, hidden }) {
    const body = $('drawer-body');
    const parts = [];
    if (card) {
      const raw = card.raw;
      const st = raw.structured || {};
      $('drawer-title').textContent = `${card.emoji ? card.emoji + ' ' : ''}${card.title}`;
      parts.push(h('dl', { class: 'kv' },
        h('dt', { text: 'Home position' }), h('dd', { text: card.live ? 'live (top of Today)' : String(card.pos) }),
        h('dt', { text: 'Time' }), h('dd', { text: `${clock(card.start)}–${clock(card.end)} (${secs(offsetOf(b, card.start))} to ${secs(offsetOf(b, card.end))})` }),
        h('dt', { text: 'Words' }), h('dd', { text: String(card.words ?? '?') }),
        h('dt', { text: 'Recordings' }), h('dd', {}, card.recordings.length ? card.recordings.map((r, i) => [i ? ' + ' : '', r, ' ', sourceTag(sourcesOf(b)[r] || 'scripted')]) : '-'),
        h('dt', { text: 'Tile state' }), h('dd', { text: String(raw.tile_state ?? '-') }),
        h('dt', { text: 'Manual end' }), h('dd', { text: raw.manual_end ? 'yes' : 'no' }),
        h('dt', { text: 'Conversation' }), h('dd', { class: 'mono', text: String(raw.id || '') }),
        raw.home_hidden ? [h('dt', { text: 'Hide reason' }), h('dd', { class: 'reason', text: String(raw.home_hidden_reason || 'hidden') })] : null));
      if (card.row && !card.row.visible) parts.push(h('p', { class: 'disagree', text: `⚠ The lab’s own rule says hidden (${card.row.hidden_reason || 'no reason'}), but the route returned it.` }));
      parts.push(h('h3', { text: 'Notes' }));
      const notes = [];
      if (st.overview) notes.push(h('p', { text: st.overview }));
      if (st.gist) notes.push(h('p', { class: 'muted', text: st.gist }));
      for (const s of st.sections || []) notes.push(h('p', {}, h('b', { text: (s.title || s.heading || '') + ' ' }), String(s.text || s.body || (Array.isArray(s.bullets) ? s.bullets.join(' · ') : ''))));
      if ((st.action_items || []).length) notes.push(h('ul', {}, st.action_items.map((a) => h('li', { text: a.description || String(a) }))));
      parts.push(...(notes.length ? notes : [h('p', { class: 'muted', text: 'No notes in the route’s response.' })]));
      parts.push(h('h3', { text: 'Transcript (seconds from each recording\u2019s start)' }));
      const segs = Array.isArray(raw.transcript_segments) ? raw.transcript_segments : [];
      if (!segs.length) parts.push(h('p', { class: 'muted', text: card.live ? 'The live route returns no transcript.' : 'No transcript lines in the route’s response (list rows may omit them).' }));
      else parts.push(h('ol', { class: 'lines' }, segs.map((s) => h('li', {},
        h('span', { class: 't', text: secs(Number(s.start)).replace('+', '') }),
        h('span', {}, h('span', { class: 'who', text: s.is_user ? 'You' : (s.speaker || 'Speaker') }), String(s.text || ''))))));
    } else {
      $('drawer-title').textContent = `Not on Home · ${hidden.handle}`;
      parts.push(h('dl', { class: 'kv' },
        h('dt', { text: 'Recordings' }), h('dd', {}, hidden.recordings.length ? hidden.recordings.map((r, i) => [i ? ' + ' : '', r, ' ', sourceTag(sourcesOf(b)[r] || 'scripted')]) : '-'),
        h('dt', { text: 'Words' }), h('dd', { text: String(hidden.words ?? '?') }),
        h('dt', { text: 'Status' }), h('dd', { text: String(hidden.row.status ?? '-') }),
        h('dt', { text: 'Manual end' }), h('dd', { text: hidden.row.manual_end ? 'yes' : 'no' }),
        h('dt', { text: 'Hide reason' }), h('dd', { class: 'reason', text: hidden.reason })));
      if (hidden.labVisible) parts.push(h('p', { class: 'disagree', text: '⚠ The lab’s own rule says visible, but the route did not return it.' }));
      parts.push(h('p', { class: 'muted', text: 'The Home route did not return this conversation, so its transcript and notes are not in home.json.' }));
    }
    body.replaceChildren(...parts);
  }

  // ---- theme and keys -------------------------------------------------------------------------
  function setTheme(theme) {
    if (theme === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    $('theme-toggle').title = `Theme: ${theme} (click for ${THEMES[(THEMES.indexOf(theme) + 1) % 3]})`;
  }
  $('theme-toggle').addEventListener('click', () => {
    const now = document.documentElement.dataset.theme || 'auto';
    setTheme(THEMES[(THEMES.indexOf(now) + 1) % 3]);
    writeHash();
  });
  $('drawer-close').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.card) { e.preventDefault(); closeDrawer(); return; }
    const inRail = document.activeElement && document.activeElement.closest && document.activeElement.closest('.rail-list');
    if (inRail && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const btns = [...document.querySelectorAll('.rail-list button')];
      const i = btns.indexOf(document.activeElement);
      const next = btns[Math.max(0, Math.min(btns.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
      if (next) next.focus();
    }
  });
  boot();
})();
