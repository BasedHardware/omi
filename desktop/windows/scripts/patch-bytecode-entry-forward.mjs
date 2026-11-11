// Make the bytecode main-entry stub FORWARD its compiled exports.
//
// THE BUG THIS FIXES (packaged builds only). The production main build bytecodes
// only the `index` entry (electron.vite.config.ts `bytecode:{chunkAlias:'index'}`).
// electron-vite replaces `out/main/index.js` with a bootstrap stub:
//
//     require("./bytecode-loader.cjs");
//     require("./index.jsc");
//
// It requires index.jsc for its SIDE EFFECTS (booting the app) but never assigns
// `module.exports = require("./index.jsc")`. So `require("../index.js")` from any
// other chunk returns index.js's own (empty) exports — `{}`. Any PLAIN chunk that
// rollup compiled to `require("../index.js").<name>(...)` — the lazy shared chunks
// backendTools / taskSyncEngine (getBackendSession) and mainChatPersonalization
// (buildDesktopChatPersonalization, getLocalActionItems, recentMemories, …) — then
// reads `undefined` and throws `index.<name> is not a function` at runtime. Dev has
// no bytecode (the require returns the real module), so it only ever bit packaged
// users. This shipped the get_goals / get_memories crash AND a silent chat-
// personalization degradation.
//
// THE FIX. Rewrite the stub to `module.exports = require("./index.jsc")`. Node's
// require returns the (fully populated) index.jsc module.exports, so every
// `require("../index.js").<name>` resolves for real — fixing the whole class at its
// root (the missing forwarding) instead of relocating modules around each symptom.
// The lazy chunks are dynamic imports that run AFTER boot, by which point the stub's
// module.exports is assigned, so there is no boot-time circular hazard.
//
// This runs as a build step after `electron-vite build` (see package.json `build`);
// `verify-bytecode.mjs` then ASSERTS the forwarding line is present, so a build
// where it is missing FAILS loud. Idempotent: a no-op if the stub already forwards.

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const ENTRY = path.join(ROOT, 'out', 'main', 'index.js')

// Match `require("./index.jsc")` / `require('./index.jsc')` NOT already prefixed by
// an assignment, so the patch is idempotent and quote-agnostic.
const JSC_REQUIRE = /(^|\n)(\s*)require\((["'])\.\/index\.jsc\3\)/

function fail(msg) {
  console.error(`[patch-bytecode-entry-forward] FAIL: ${msg}`)
  process.exit(1)
}

function main() {
  if (!existsSync(ENTRY)) {
    fail(`no entry at ${ENTRY} — run electron-vite build first`)
  }
  const code = readFileSync(ENTRY, 'utf8')

  if (/module\.exports\s*=\s*require\((["'])\.\/index\.jsc\1\)/.test(code)) {
    console.log(
      '[patch-bytecode-entry-forward] entry already forwards index.jsc exports (idempotent).'
    )
    return
  }

  // Refuse to patch an unexpected stub shape (electron-vite bytecode plugin changed):
  // silently mis-patching the entry would be worse than failing the build.
  if (!code.includes('bytecode-loader') || !JSC_REQUIRE.test(code)) {
    fail(
      'unexpected entry stub shape — expected the electron-vite bytecode bootstrap ' +
        '(require loader + require("./index.jsc")). Did the bytecode plugin change? Refusing to patch.'
    )
  }

  const patched = code.replace(
    JSC_REQUIRE,
    (_m, lead, indent, q) => `${lead}${indent}module.exports = require(${q}./index.jsc${q})`
  )
  if (
    patched === code ||
    !/module\.exports\s*=\s*require\((["'])\.\/index\.jsc\1\)/.test(patched)
  ) {
    fail('patch did not apply — the forwarding line is still absent after replace.')
  }
  writeFileSync(ENTRY, patched)
  console.log('[patch-bytecode-entry-forward] OK — entry now forwards index.jsc exports.')
}

main()
