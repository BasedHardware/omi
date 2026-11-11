// Single source of truth for the KG write-worker's native-module runtime closure.
//
// WHY THIS EXISTS
// kgWorker.js is loaded via `new Worker(path)` from a REAL path on disk
// (resources/app.asar.unpacked/out/main/kgWorker.js — see src/main/ipc/kg.ts
// workerScriptPath() and the `out/main/kgWorker.js` asarUnpack glob). Unlike the
// Electron main process, which runs inside the asar virtual-fs and can therefore
// `require()` transparently across the packed/unpacked boundary, the worker's
// module resolution is plain real-fs anchored at app.asar.unpacked — it NEVER
// crosses back into app.asar. So every package the worker require()s at runtime
// must physically exist under app.asar.unpacked/node_modules.
//
// THE BUG THIS FIXES
// better-sqlite3 has a native .node addon, so electron-builder AUTO-unpacks it —
// but its pure-JS runtime dep `bindings` (and bindings' dep `file-uri-to-path`)
// stayed inside app.asar. The worker resolved better-sqlite3 fine, then died with
// "Cannot find module 'bindings'" the moment better-sqlite3 called require('bindings').
//
// THE RUNTIME REQUIRE CHAIN (traced from installed source — re-trace on a
// better-sqlite3 bump):
//   better-sqlite3   → require('bindings')          (lib/database.js)
//   bindings         → require('file-uri-to-path')  (bindings.js, top-level)
//   file-uri-to-path → (no runtime deps)
//
// NOT INCLUDED ON PURPOSE: better-sqlite3 also lists `prebuild-install` in its
// package.json "dependencies", but that is an INSTALL-TIME tool (downloads the
// prebuilt .node) — lib/ never require()s it at runtime. A naive dependency-graph
// walk would over-unpack prebuild-install's large tree for zero runtime benefit,
// so this list is the precise, source-traced runtime closure instead.
//
// better-sqlite3 itself is listed explicitly (not left to electron-builder's
// implicit native-module auto-unpack) so the whole worker closure is declared in
// one place and the intent survives any change to auto-unpack heuristics.

export const KGWORKER_NATIVE_PACKAGES = ['better-sqlite3', 'bindings', 'file-uri-to-path']

export const KGWORKER_NATIVE_UNPACK_GLOBS = KGWORKER_NATIVE_PACKAGES.map(
  (name) => `node_modules/${name}/**`
)
