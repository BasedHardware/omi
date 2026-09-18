// electron-builder afterPack hook: correct chalk's version in the packaged
// app.asar.unpacked tree.
//
// THE BUG: @earendil-works/pi-coding-agent needs chalk@5.6.2 as a real runtime
// dependency (spawned as a plain-Node child by src/main/codingAgent/piMono.ts —
// see gen-pimono-unpack.mjs's header comment). pnpm's hoisted node_modules keeps
// TWO copies on disk: chalk@4.1.2 flat at top-level (needed only by dev/build-only
// tooling — electron-builder's own internals, eslint) and chalk@5.6.2 nested under
// node_modules/@earendil-works/pi-coding-agent/node_modules/chalk (the one pi
// actually needs). electron-builder's own packing step collapses same-named
// node_modules entries to one path and — empirically, reproducibly, confirmed by
// spawning the actual packaged pi-coding-agent CLI — always keeps the top-level
// copy, discarding the nested one. That leaves pi-coding-agent trying to run
// against chalk@4 (CJS, no "./static"-style modern exports) and crashing before
// the app can even advertise its tools, silently breaking the packaged app's AI
// chat with no build-time signal.
//
// WHY NOT A pnpm OVERRIDE (like jiti/glob/minimatch/hosted-git-info/ignore/semver
// in pnpm-workspace.yaml, which hit this exact same bug and got fixed that way):
// chalk 5 is ESM-only. Forcing every consumer to 5.6.2 breaks electron-builder's
// own CJS `require('chalk')` at build time — confirmed directly: `TypeError:
// chalk.underline is not a function` from node_modules/electron-builder/src/cli/
// cli.ts. So both versions must keep coexisting in node_modules; the fix instead
// corrects only the PACKAGED copy, after packing, to what pi-coding-agent needs.
//
// This only affects pi-coding-agent's own plain-Node child process — chalk is not
// imported anywhere in src/ (grepped), so nothing else in the packaged app reads
// from this path.
import { existsSync, readFileSync, rmSync, cpSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WIN_ROOT = join(HERE, '..')

// pi-coding-agent's own nested copy is the source of truth for what gets shipped —
// never hardcode a version here; whatever pnpm actually resolved for pi wins.
const SOURCE_CHALK = join(
  WIN_ROOT,
  'node_modules',
  '@earendil-works',
  'pi-coding-agent',
  'node_modules',
  'chalk'
)

// electron-builder's output layout differs by platform (Windows/Linux: flat
// resources/app.asar.unpacked; macOS: nested under <Product>.app/Contents/
// Resources/), so search for the app.asar.unpacked dir rather than hardcoding a
// per-platform path.
function findAsarUnpacked(root) {
  const stack = [root]
  while (stack.length > 0) {
    const dir = stack.pop()
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const full = join(dir, entry.name)
      if (entry.name === 'app.asar.unpacked') return full
      stack.push(full)
    }
  }
  return null
}

export default async function afterPack(context) {
  if (!existsSync(join(SOURCE_CHALK, 'package.json'))) {
    throw new Error(
      `[fix-pimono-chalk-unpack] FAIL: no nested chalk at ${SOURCE_CHALK} — ` +
        `@earendil-works/pi-coding-agent's dependency tree changed shape. Re-check ` +
        `whether this fix (and its "why not a pnpm override" reasoning) still applies.`
    )
  }
  const sourceVersion = JSON.parse(readFileSync(join(SOURCE_CHALK, 'package.json'), 'utf8')).version

  const asarUnpacked = findAsarUnpacked(context.appOutDir)
  if (!asarUnpacked) {
    throw new Error(
      `[fix-pimono-chalk-unpack] FAIL: no app.asar.unpacked found under ${context.appOutDir}.`
    )
  }
  const destChalk = join(asarUnpacked, 'node_modules', 'chalk')
  if (!existsSync(destChalk)) {
    throw new Error(
      `[fix-pimono-chalk-unpack] FAIL: no packaged chalk at ${destChalk} — ` +
        `expected pi-mono's asarUnpack closure (gen-pimono-unpack.mjs) to have put one there.`
    )
  }

  rmSync(destChalk, { recursive: true, force: true })
  cpSync(SOURCE_CHALK, destChalk, { recursive: true })
  console.log(
    `[fix-pimono-chalk-unpack] OK — replaced packaged chalk with pi-coding-agent's ` +
      `own chalk@${sourceVersion} at ${destChalk}`
  )
}
