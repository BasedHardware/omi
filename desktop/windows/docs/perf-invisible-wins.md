# Invisible performance wins — Omi Windows desktop

**Scope:** performance techniques that are **invisible to users** — zero change to functionality, interaction, or visual design. Same pixels, same behavior, same feature set. Anything that would remove an animation, reduce visual quality, change latency a user could feel, or alter UX is **excluded** (and where a tempting technique fails that bar, it's listed as EXCLUDED with the reason).

**Status:** research draft, uncommitted. Prioritization = expected win × confidence ÷ implementation risk. Items marked _[measure]_ require a profiling pass to validate before/after — pair them with the app's existing perf marks (`window.omi?.perfMark`, `app.getAppMetrics()`, `renderer.info`).

---

## What is ALREADY optimized (do NOT redo — credit, don't re-recommend)

The app has had multiple perf passes. Verified in-tree today:

- **d3-force-3d simulation** (`src/renderer/src/lib/useGraphSimulation.ts`): module-scoped layout cache (unchanged node-set → zero physics), one synchronous batched settle instead of ~170 live frames, alpha-decay stops ticking when settled (no idle CPU), imperative `liveNode()` reads — **zero per-frame React state**. Fully handled.
- **Orb WebGL loop** (`src/renderer/src/orb/orbAnimator.ts`): `OrbAnimator` self-throttles rAF to **30fps idle / 60fps active / 0fps hidden**. The always-on overlay is already disciplined.
- **30Hz level stream**: playback levels go into a `useRef` (`playbackLevelRef`) + a lightweight signal bus (`playbackLevelBus` `createSignal`) read imperatively — **not** React `setState` per sample. Correct pattern already in place.
- **Renderer code-splitting**: the whole 3D stack (three + r3f + drei + d3-force-3d, ~1MB) is `React.lazy`'d via `LazyBrainGraph.tsx`; `@sentry/electron/renderer` and `onnxruntime-web` are dynamically `import()`ed. Startup bundle already trimmed.
- **BrainGraph off-screen saving**: `frameLoop='demand'` on Memories, `pauseWhenHidden` unmounts the canvas on hidden tabs. Sphere segments already cut 32→16.
- **SQLite**: main `omi.db` is `journal_mode=WAL` + `busy_timeout=5000`; the knowledge-graph writes run in a **worker_thread** (`kgWorker.ts`) with its own `synchronous=NORMAL` connection; a dedicated read-only connection exists.
- **d3 edge buffers**: `GraphEdge` reuses one 6-float array across frames (no per-frame allocation).

So the remaining wins are narrower and more surgical than a greenfield app. They concentrate in: the **BrainGraph GPU draw path** (still per-node/per-edge React + three objects), **SQLite pragmas + statement hoisting**, and **Electron timer/throttle policy**.

---

## App-specific findings (verified in-tree, independent of external research)

These are concrete, already-mappable:

1. **BrainGraph is per-node / per-edge, not batched.** `src/renderer/src/components/graph/BrainGraph.tsx`: every node is a `GraphNodeMesh` with 3 separate sphere meshes (core/halo/bloom) + a troika `<Text>` label, **each running its own `useFrame`**; every edge is a `GraphEdge` with its own `useFrame` + draw call. For N nodes / E edges that's ~3N+E draw calls and N+E per-frame JS callbacks. This is the single largest untapped GPU/CPU win (see Area 1). Applies most on the interactive full-screen KG page (`frameloop='always'`).
2. **Main `omi.db` sets no read-tuning pragmas.** `src/main/ipc/db.ts` sets only WAL + busy_timeout. `cache_size` / `mmap_size` / `temp_store=MEMORY` are unset — pure read-speed wins with **no durability tradeoff** (see Area 5).
3. **`store.ts` re-`prepare()`s SQL inline per call** (`src/main/agentKernel/store.ts`, many `db?.prepare(...)` sites in hot methods). better-sqlite3 caches compiled statements internally, but hoisting to module/instance scope removes the per-call lookup (see Area 5).
4. **Main window keeps `backgroundThrottling:false`** (`src/main/index.ts`) purely so Rewind's background screen-capture keeps sampling on renderer timers when hidden. If that sampling moved to a main-process timer / worker, the hidden main window could be throttled again with no behavior change (see Area 2). _[measure]_
5. **22 `setInterval` sites in main** (rewind sweeps, updater, goal/task polls, foreground monitors, glow/bar watches). Candidate for coalescing / visibility-gating — but several are behavior-load-bearing (Rewind), so _[measure]_ and gate carefully (see Area 2).

---

## Top 10 — prioritized (win × confidence ÷ risk)

Ranked across all areas. **★ = do-first (top 5).** _[measure]_ = validate with a profiling pass before/after.

| # | Technique | Area | Win | Conf | Risk | Where |
|---|-----------|------|-----|------|------|-------|
| 1 ★ | SQLite read pragmas: `cache_size=-64000`, `temp_store=MEMORY` on the main connection | 5 | Med-High | High | Very low | `src/main/ipc/db.ts` (next to WAL block) |
| 2 ★ | Merge all graph edges into one `LineSegments2` / `LineSegmentsGeometry` | 1 | High (KG page) | High | Low-Med | `BrainGraph.tsx` `GraphEdges`/`GraphEdge` |
| 3 ★ | InstancedMesh ×3 for node sphere layers + `three-instanced-uniforms-mesh` for per-node emissive pulse | 1 | High (KG page) | Med | Med | `BrainGraph.tsx` `GraphNodeMesh` |
| 4 ★ | Zero-allocation AudioWorklet `process()` (hoist scratch buffers) + transferable-list `postMessage` for PCM | 3/4 | Med | High | Very low | `pcmWorkletCore.ts`, `playerWorklet.ts`, `pcmWorklet.ts` |
| 5 ★ | Hoist inline `db.prepare()` (~240 sites) to module/instance-scoped cached statements | 5 | Med | High | Low | `store.ts`, `taskStore.ts`, `db.ts` (pattern: `applyFileIndexDiff` db.ts:944) |
| 6 | Single consolidated `useFrame` (enables #2/#3; kills N+E per-frame callbacks) | 1 | High | High | Med | `BrainGraph.tsx` (GraphScene owns one loop) |
| 7 | `electron-vite` `bytecodePlugin` for main+preload (V8 compile skip at startup) | 2 | Med | High | Low-Med | `electron.vite.config.*` (+ CI regen per Electron ver) |
| 8 | Lazy `import()` remaining heavy main/renderer deps (firebase, ws, koffi paths) | 2 | Med | High | Low | main entry + renderer route boundaries |
| 9 | Demand-driven **bar orb** rendering (`frameloop='demand'` + `invalidate()` from tween/amplitude ticks) — bar orb ONLY, NOT the graph | 2 | Med | Med | Med | `orbAnimator.ts` / Orb Canvas — coordinate w/ amplitude work |
| 10 | Transaction-wrap remaining un-batched bulk-insert loops | 5 | Med (sync/import) | High | Low | audit `taskStore.ts`, rewind embedding/caption inserts |

Two items are deliberately **NOT** in the do-first set despite high appeal: `synchronous=NORMAL` (durability tradeoff the team already litigated — needs Chris's sign-off, see Area 5) and moving the KG LIKE/similarity scans to a worker thread (larger refactor, [measure] first).

---

## Cross-cutting: two conflicts resolved per-surface (read before implementing)

1. **`frameloop='demand'` is per-surface, not global.**
   - **Graph canvas (KG page, onboarding): keep `'always'` — do NOT switch to demand.** The scene animates continuously (sim easing + emissive pulse + label depth-fade every frame), so `invalidate()` would fire every frame anyway = `'always'` with extra bookkeeping and a real jank/blank risk. Memories already uses `'demand'` correctly because it settles. EXCLUDED for the always-animating path.
   - **Bar orb: demand IS the right call.** The orb is tween-driven with genuine at-rest periods, and `OrbAnimator` already self-throttles to 0fps hidden. Key doc fact: **Electron window-occlusion tracking is macOS-only**, so `document.visibilityState` is useless for the always-visible bar on Windows — demand rendering driven from tween + amplitude ticks is the only honest idle-stop. Coordinate with the in-flight amplitude work before touching this loop.

2. **`synchronous` claim needs a runtime check.** The scaffold (and the db.ts:384-387 comment) assert the main connection stays `FULL`. SQLite's default IS `FULL`, so the comment is consistent — but confirm empirically with `db.pragma('synchronous')` before any doc or change relies on it. Do not ship a lowered value here without Chris.

---

## Area 1: 3D force-graph rendering (render path only — sim is already optimized)

Biggest untapped GPU/CPU win in the app. Today `BrainGraph.tsx` draws N nodes as 3 separate meshes each + a troika `<Text>`, E edges as separate `<Line>`s, with **N+E separate `useFrame` callbacks per frame**. On the interactive KG page (`frameloop='always'`, dense server graph) that is the dominant cost.

- **★ Merge all edges into one `LineSegments2` (`LineSegmentsGeometry`)** — one draw call for every edge instead of E, one shared position buffer updated once per frame instead of E `setPositions([6])` calls. This is exactly how `vasturiano/three-forcegraph` / `react-force-graph` batch links. Win: high; risk: low-med (fat-line width via `Line2` material `linewidth` in world/px units — match the current `lineWidth={0.8}`/opacity so pixels are identical). Maps to `GraphEdges`/`GraphEdge`. Sketch: build one `LineSegmentsGeometry`, write all endpoints into its instance buffer inside the single loop, set `.needsUpdate`. Source: three.js examples `lines/LineSegments2`; `vasturiano/react-force-graph`.
- **★ InstancedMesh for the node spheres — one InstancedMesh per layer (core/halo/bloom), 3 draw calls total instead of 3N.** The per-node emissive pulse (which blocks naive instancing with a shared material) is solved by `pmndrs/three-instanced-uniforms-mesh` — its `setUniformAt('emissiveIntensity', i, value)` patches the material shader to source a per-instance attribute, so the pulse math stays byte-identical (still a scalar uniform, just instanced). Win: high on dense graphs; risk: med — **the real subtlety is picking, not pixels**: if nodes are clickable/hoverable, per-mesh `onClick` must become `instanceId`-based hit-testing (a code-shape change even though the render is pixel-identical), so verify hover/click behavior is preserved. Maps to `GraphNodeMesh`. Source: three.js `InstancedMesh` docs; `three-instanced-uniforms-mesh`.
- **★ Consolidate the per-node/per-edge `useFrame`s into ONE `useFrame` in `GraphScene`** — the canonical r3f "one animation loop, mutate imperatively, never setState in useFrame" pattern. **Accuracy note:** r3f already batches every `useFrame` into a single internal rAF, so the win is NOT "fewer callbacks" — it's (a) eliminating the **per-frame array allocation** each edge's `setPositions([6])` does (fresh array × E edges every frame = GC pressure), and (b) it's the mechanical *prerequisite* for instancing (one owner must write the shared instance/line buffers). Copy the lerp/pulse/depth-fade formulas verbatim so output is identical. Win: high; risk: low-med (pure refactor of *where* the same math runs). Source: r3f "Scaling performance" + Pitfalls docs; reference impl `vasturiano/r3f-forcegraph` (whole graph driven by one `useFrame(() => fg.tickFrame())`).
- **troika text at scale: `preloadFont` once + keep the shared SDF atlas; batch `Text.sync()`.** troika already shares one glyph atlas across all `<Text>` instances, so labels are cheaper than they look — but preloading the font avoids first-mount sync stalls, and the existing 1/8-quantized `fillOpacity` re-sync (already in `GraphNodeMesh`) is the right call. Keep it. Win: low-med; risk: low. Source: `protectwise/troika` troika-three-text README (`preloadFont`, `sync`).
- **Skip matrix updates for settled nodes: `matrixAutoUpdate=false` + manual `updateMatrix()` only while a node is still easing.** Once `distanceToSquared(target) < 0.01` (already computed), stop recomputing the world matrix. Win: low-med on large settled graphs; risk: low. Maps to `GraphNodeMesh` settle branch.
- **Instrument with `renderer.info.render.calls` / `.triangles`** to prove each cut. _[measure]_ — this is the acceptance gate for every Area 1 item. Source: three.js `WebGLRenderer.info`.
- **EXCLUDED — `frameloop='demand'` on the graph canvas** (continuous animation ⇒ every-frame invalidate = `'always'` + overhead + blank-on-resize risk). See cross-cutting note.
- **EXCLUDED — dpr / antialias downgrades** (visible edge quality change on the orb-adjacent crisp-rim requirement). Keep `dpr={[1,2]}` + `antialias:true`.

## Area 2: Electron app efficiency

Startup code-splitting is already strong (three/Sentry/onnxruntime lazy). Remaining wins are startup compile, resident-idle CPU, and the transparent-window GPU cost.

- **★ `electron-vite` `bytecodePlugin` for main + preload** — ships V8 bytecode so Electron skips parse/compile at boot. Win: med (startup); risk: low-med — **must regenerate per Electron version in CI** (bytecode is version-locked), else a version bump breaks boot. Maps to `electron.vite.config.*`. Source: electron-vite.org "Source Code Protection" (`bytecodePlugin`).
- **Lazy `import()` remaining heavy deps** (firebase, ws, koffi-bound modules) so they load on first use, not at process start — Windows `require()` file I/O is disproportionately expensive vs macOS. Win: med; risk: low. Source: VS Code startup-perf writeups; Electron performance guide (electronjs.org/docs/latest/tutorial/performance).
- **Demand-driven bar orb** (frameloop='demand' + invalidate from tween/amplitude) — see cross-cutting note #1; the only honest idle-stop on Windows because occlusion tracking is macOS-only. Win: med resident CPU; risk: med. Coordinate w/ amplitude work.
- **Narrow `backgroundThrottling:false`** on the hidden main window: move Rewind's background sampling to a **main-process timer / worker** so the renderer no longer needs full-rate timers while hidden, then let Chromium throttle it. Win: med resident CPU; risk: med — **hard caveat: electron/electron#42378** (Windows windows can go blank/frozen after minutes when throttling re-enabled) — gate behind a real test. _[measure]_ Maps to `src/main/index.ts` + `src/main/rewind/*`.
- **Transparent-window DWM GPU audit** for the glow + toast windows only (never the bar): `transparent:true` on Windows has measured DWM compositor cost (electron/electron#39895 reported 16–18% → <1% GPU when a transparent window was made opaque). Verify each transparent surface truly needs alpha. Win: med GPU; risk: low (audit-only) — do NOT touch the bar (needs click-through alpha). _[measure]_
- **rAF-aligned IPC batching of the 30Hz level stream** — coalesce level messages to one per paint frame (bounded by a single frame, so imperceptible) to cut IPC/GC churn. Win: low-med; risk: low-med (perceptibility check required — must stay ≤1 frame). Maps to `voiceHub:playbackLevel` send path. Source: Electron IPC perf guidance.
- **Timer coalescing** across the 22 `setInterval` sites — align cadences / gate the non-load-bearing ones on activity to reduce CPU wakeups (battery). Win: low; risk: med (several are Rewind/behavior-load-bearing — do NOT gate those). _[measure]_ Maps to the interval inventory in "App-specific findings".
- **Measurement gate: `app.getAppMetrics()`** for per-process CPU/mem before/after. Source: electronjs.org/docs `app.getAppMetrics`.
- **EXCLUDED — `paintWhenInitiallyHidden:false`** for the capture window (it runs getUserMedia/AudioContext offscreen; suppressing paint risks the capture path). Keep as-is.

## Area 3+4: React hot-path & Web Audio

The ref + `playbackLevelBus` signal pattern is already correct — most wins here are audio-worklet allocation hygiene, not React.

- **★ Zero-allocation AudioWorklet `process()`** — hoist all scratch buffers to the processor constructor; never allocate inside `process()` (runs on the audio render thread every 128-sample quantum). Win: med (audio-thread GC/glitch avoidance); risk: very low. Maps to `pcmWorkletCore.ts`, `playerWorklet.ts`. Source: MDN AudioWorklet; web.dev "Enter AudioWorklet" (Paul Adenot / padenot guidance).
- **★ Transferable-list `postMessage` for PCM buffers** (`postMessage(chunk, [chunk.buffer])`) so audio frames are transferred, not structured-cloned — a large-buffer copy costs hundreds of ms vs ~6ms transferred (Chrome). **Reconcile with the zero-alloc rule above:** a transferred buffer becomes zero-length on the sender, which conflicts with "pre-allocate once and reuse" — resolve with a small **round-robin pool of N pre-allocated buffers** cycled per frame, not one buffer reused-and-transferred. Win: med; risk: very low. Maps to worklet↔main `port.postMessage` in `pcmWorklet.ts`/`playerWorklet.ts`. Source: MDN Transferable objects; Chrome "Transferable objects — lightning fast".
- **★ Per-frame allocation audit of draw callbacks** — confirm no `new`/array-literal churn in the graph `useFrame`s (the edge loop already reuses its array — good; verify node loop). Win: low-med; risk: very low. _[measure]_ with why-did-you-render / DevTools Profiler as the acceptance gate.
- **`useSyncExternalStore` ONLY for any straggler doing `useEffect`+`setState` off the level bus** — the correct React 18 primitive for subscribing to an external high-freq store with tear-free selectors. **Do NOT convert existing ref-based consumers** (that would be a regression — refs are already faster than a subscribe/selector at 30Hz). Win: low; risk: med if misapplied. Source: react.dev `useSyncExternalStore`.
- **Coalesce independent rAF loops** if 2+ exist so subscribers share one loop. Win: low; risk: low. _[measure]_ (inventory first — Orb already owns its loop).
- **`binaryType='arraybuffer'` cross-provider audit** — verify the OpenAI realtime lane sets it (Gemini lane already does, per prior work) so realtime frames arrive as ArrayBuffers, not Blobs needing async decode. Win: low-med (correctness+perf); risk: low. Maps to the realtime WS factories.
- **DEPRIORITIZED — SharedArrayBuffer ring buffer** between worklet and main: Electron COOP/COEP requirements make it fragile, and `postMessage` transfer is fine at 30Hz (padenot's rule: SAB only when message rate is the bottleneck). Not worth it here.
- **EXCLUDED — throttling/`useDeferredValue` on the level signal, or larger audio quanta** (all perceptible: orb smoothness / audio latency). Keep current cadence.

## Area 5: SQLite in Electron main

### Pure invisible wins (no durability tradeoff)

- **★ `cache_size` + `temp_store=MEMORY` pragmas** on the main connection, next to the existing WAL block (`db.ts` ~line 388). `PRAGMA cache_size=-64000` (64MB page cache) and `PRAGMA temp_store=MEMORY` are pure read/sort-speed wins with zero durability cost. Win: med-high on read-heavy IPC; risk: very low. Source: sqlite.org/pragma.html; phiresky "SQLite performance tuning".
- **★ Hoist inline `db.prepare()` (~240 sites across main) to cached prepared statements** — module/instance-scoped, prepared once. better-sqlite3 has an internal statement cache, but re-calling `prepare(sql)` per IPC hit still costs a lookup + wrapper alloc. The in-tree exemplar is `applyFileIndexDiff` (db.ts:944): statements prepared once, reused inside one `d.transaction()`. Win: med; risk: low. Maps to `store.ts`, `taskStore.ts` hot methods. Source: `WiseLibs/better-sqlite3` performance.md.
- **★ Transaction-wrap remaining un-batched bulk loops** — one fsync instead of N implicit commits. Several paths already do this correctly (`applyFileIndexDiff`, taskStore reindex) — audit the rest (rewind embedding inserts, caption-event batches, import fanout) for per-row implicit commits. Win: med-high on bulk paths; risk: low. Source: better-sqlite3 `Database#transaction` docs.
- **`.pluck()` / `.raw()` / `.iterate()`** on large single-column or large-result reads to skip per-row object materialization. Win: low-med; risk: low (changes return shape at the call site only — verify each). Source: better-sqlite3 api.md.
- **`mmap_size`** (e.g. `PRAGMA mmap_size=268435456`) — memory-mapped I/O read win, but **measure on Windows specifically** before committing (mmap behavior/benefit differs on Windows). _[measure]_ Win: med (reads); risk: low. Source: sqlite.org/mmap.html.
- **`PRAGMA optimize` on clean shutdown (and hourly)** + occasional `ANALYZE` — keeps the query planner's stats fresh; invisible, improves plan quality over a long-lived DB. Win: low-med (compounds over time); risk: very low. Source: sqlite.org/lang_analyze.html, pragma.html (`optimize`).

### Durability-gated / larger (NOT do-first — require sign-off or measurement)

- **`synchronous=NORMAL` on the main connection** — under WAL, NORMAL only risks the **last transaction on OS-crash/power-loss** (an app crash is still safe). Write-latency win is real, but the team **deliberately chose FULL** (db.ts:384-387) for `local_conversation` etc. **Needs Chris's explicit sign-off + a runtime `db.pragma('synchronous')` check first.** Source: sqlite.org/wal.html (NORMAL guarantee).
- **`wal_autocheckpoint` tuning** — can smooth write latency but risks checkpoint starvation with the two-writer (main + kgWorker) setup. Measure the WAL growth first. _[measure]_ Source: sqlite.org/wal.html.
- **Move KG `queryKgNodes` OR-of-LIKE full-table scan (db.ts:1205) + the rewind vector-similarity scan (db.ts:1673) into the existing `kgWorker` worker_thread pattern** — these are the two confirmed main-thread-blocking scans. Bigger refactor; the invisible payoff is eliminating main-process jank during search. _[measure]_ Win: med-high (responsiveness); risk: med. Source: better-sqlite3 worker_threads guidance; Actual Budget's blocking-main-process case study.
- **`foreign_keys`** — verification-only (confirm it's set as intended); not a perf lever.

---

## Measurement plan (pair every _[measure]_ item with this)

- **Renderer/graph:** `renderer.info.render.calls`/`.triangles` before/after each Area 1 change; r3f `<Perf>` (leva) or DevTools Performance for frame time on the KG page with a dense real graph (not the empty state).
- **React re-renders:** `why-did-you-render` or DevTools Profiler as the acceptance gate for hot-path items (Area 3).
- **Process CPU/mem:** `app.getAppMetrics()` sampled over a resident-idle window (bar alive, main hidden) before/after Area 2 throttle/timer changes.
- **SQLite:** wrap hot IPC handlers in a timing log; `PRAGMA compile_options` / `db.pragma('cache_size')` to confirm pragmas took; `EXPLAIN QUERY PLAN` on the LIKE/similarity scans.
- **Startup:** the existing `window.omi?.perfMark` / `perfFirstPaint` marks bracket window-created→renderer-eval→first-paint for Area 2 bytecode/lazy-import work.

---

## Sources

**Area 1 — 3D force-graph**
- r3f Scaling Performance — https://r3f.docs.pmnd.rs/advanced/scaling-performance
- r3f Pitfalls (mutate in useFrame, no setState/alloc in loop) — https://r3f.docs.pmnd.rs/advanced/pitfalls
- three.js InstancedMesh — https://github.com/mrdoob/three.js/blob/dev/docs/pages/InstancedMesh.html.md
- three.js LineSegmentsGeometry / LineSegments2 — https://threejs.org/docs/pages/LineSegmentsGeometry.html · https://threejs.org/docs/pages/LineSegments2.html
- three-instanced-uniforms-mesh — https://www.npmjs.com/package/three-instanced-uniforms-mesh · https://protectwise.github.io/troika/three-instanced-uniforms-mesh/
- troika-three-text README — https://github.com/protectwise/troika/blob/main/packages/troika-three-text/README.md · scale caveat: https://github.com/protectwise/troika/issues/117
- vasturiano/r3f-forcegraph — https://github.com/vasturiano/r3f-forcegraph
- three.js WebGLRenderer.info (draw-call measurement) — https://threejs.org/docs/pages/Info.html
- static-object matrix updates — https://discourse.threejs.org/t/preventing-matrix-updates-for-static-objects/74262 · https://github.com/pmndrs/react-three-fiber/discussions/2769

**Area 2 — Electron**
- electron-vite Source Code Protection (bytecodePlugin) — https://electron-vite.org/guide/source-code-protection
- electron-vite Dependency Handling — https://electron-vite.org/guide/dependency-handling
- V8 code caching — https://v8.dev/blog/code-caching-for-devs · https://v8.dev/blog/code-caching
- Inkdrop "launch 1000ms faster" — https://www.devas.life/how-to-make-your-electron-app-launch-1000ms-faster/
- Palette (Slack/Notion/VSCode perf) — https://palette.dev/blog/improving-performance-of-electron-apps
- backgroundThrottling blank-window bug (Windows) — https://github.com/electron/electron/issues/42378 · https://github.com/electron/electron/issues/31016
- transparent-window DWM GPU cost — https://github.com/electron/electron/pull/39895 · https://github.com/electron/electron/issues/10994
- Electron web-preferences / BrowserWindow (occlusion is macOS-only) — https://github.com/electron/electron/blob/main/docs/api/web-preferences.md · https://github.com/electron/electron/blob/main/docs/api/browser-window.md
- Electron IPC v8-serialization — https://github.com/electron/electron/pull/20214 · https://github.com/electron/electron/pull/8953
- Electron performance guide / getAppMetrics — https://www.electronjs.org/docs/latest/tutorial/performance · https://github.com/electron/electron/blob/main/docs/api/app.md

**Area 3+4 — React hot-path & Web Audio**
- react.dev useSyncExternalStore — https://react.dev/reference/react/useSyncExternalStore
- r3f Pitfalls (no setState in loop) — https://github.com/pmndrs/react-three-fiber/blob/master/docs/advanced/pitfalls.mdx
- MDN AudioWorklet — https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Using_AudioWorklet · https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletProcessor/process
- Chrome Audio Worklet design pattern — https://developer.chrome.com/blog/audio-worklet-design-pattern/
- Loke.dev "Stop Allocating Inside AudioWorkletProcessor" — https://loke.dev/blog/stop-allocating-inside-audioworkletprocessor
- MDN Transferable objects — https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Transferable_objects · https://developer.chrome.com/blog/transferable-objects-lightning-fast
- padenot/ringbuf.js + SAB/COOP-COEP caveats — https://github.com/padenot/ringbuf.js/ · https://github.com/electron/electron/issues/31789 · https://web.dev/articles/cross-origin-isolation-guide
- MDN WebSocket.binaryType — https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/binaryType
- why-did-you-render — https://github.com/welldone-software/why-did-you-render

**Area 5 — SQLite**
- better-sqlite3 api / performance / threads / benchmark — https://github.com/wiselibs/better-sqlite3/blob/master/docs/api.md · /performance.md · /threads.md · /benchmark.md
- SQLite pragma / optimize / WAL — https://sqlite.org/pragma.html · https://sqlite.org/pragma.html#pragma_optimize · https://sqlite.org/wal.html
- phiresky "SQLite performance tuning" — https://phiresky.github.io/blog/2020/sqlite-performance-tuning/
- WAL + synchronous=NORMAL durability — https://sqlite-users.sqlite.narkive.com/Zy5Lrn6W/wal-durability-and-synchronous-normal
- Actual Budget "Horror of Blocking Electron's Main Process" — https://medium.com/actualbudget/the-horror-of-blocking-electrons-main-process-351bf11a763c
