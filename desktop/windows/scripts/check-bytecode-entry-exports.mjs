// Build-output guard: no PLAIN main chunk may read a named export off the bytecode
// `index` entry.
//
// WHY. The production main build bytecodes ONLY the `index` entry (electron.vite.config.ts
// `bytecode: { chunkAlias: 'index' }`). The emitted `index.js` is a stub that
// side-effect-requires `index.jsc` and NEVER forwards its exports, so at runtime
// `require("../index.js")` returns `{}`. Any plain chunk that compiled to
// `require("../index.js").<name>(...)` therefore throws `index.<name> is not a function`
// — but ONLY in packaged builds (dev has no bytecode). This exact bug made get_goals /
// get_memories / the REST search tools fail on shipped Windows builds while dev was green.
//
// This guard greps the built chunks for `index.<forbidden>` references and fails the
// build if any reappear, so the class can't silently regress. It runs after
// `electron-vite build` (see package.json `build`). Add a symbol here the moment a new
// getBackendSession-style entry export starts being consumed from a lazy chunk.
//
// Scope: the symbols this PR fixed (the backend-session accessors). `mainChatPersonalization`
// has the same latent shape for other symbols and is tracked separately; when it is fixed,
// add its symbols here too.

import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const CHUNKS_DIR = path.join(ROOT, 'out', 'main', 'chunks')

// Named exports that live in the (now plain) backend-session chunk. A plain chunk
// reading these off `index` means session.ts leaked back into the bytecode entry.
const FORBIDDEN = ['getBackendSession', 'getAbortSignal']

function main() {
  let files
  try {
    files = readdirSync(CHUNKS_DIR).filter((f) => f.endsWith('.js'))
  } catch {
    console.error(
      `[check-bytecode-entry-exports] no chunks dir at ${CHUNKS_DIR} — run electron-vite build first`
    )
    process.exit(1)
  }

  const violations = []
  for (const f of files) {
    const text = readFileSync(path.join(CHUNKS_DIR, f), 'utf8')
    // Only meaningful when the chunk actually pulls the bytecode entry in as a namespace.
    if (!/require\(["']\.\.\/index\.js["']\)/.test(text)) continue
    for (const name of FORBIDDEN) {
      if (new RegExp(`index\\.${name}\\b`).test(text)) {
        violations.push({ file: f, symbol: name })
      }
    }
  }

  if (violations.length > 0) {
    console.error(
      '[check-bytecode-entry-exports] FAIL — plain chunk(s) read a bytecode-entry export:'
    )
    for (const v of violations) {
      console.error(`  ${v.file}: index.${v.symbol}  →  undefined at runtime in packaged builds`)
    }
    console.error(
      'Fix: keep the module defining that export OUT of the bytecode `index` entry via ' +
        'manualChunks in electron.vite.config.ts (see the `backend-session` chunk).'
    )
    process.exit(1)
  }

  console.log(
    `[check-bytecode-entry-exports] OK — ${files.length} chunk(s) scanned, no forbidden bytecode-entry export reads.`
  )
}

main()
