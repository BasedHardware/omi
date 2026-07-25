import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// build:linux (Desktop Windows CI's Linux-package smoke) invoked electron-builder
// without `--publish never`, so it tried to publish and failed on a missing
// GH_TOKEN — reddening Desktop Windows CI on main. build:win already had the flag.
// Pin that every electron-builder *packaging* script (--win/--mac/--linux) opts
// out of publishing: a smoke/CI build must never attempt a release.

const pkg = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'package.json'), 'utf-8')
)

const packagingScripts = Object.entries(pkg.scripts ?? {}).filter(
  ([, cmd]) =>
    cmd.includes('electron-builder') &&
    (cmd.includes('--win') || cmd.includes('--mac') || cmd.includes('--linux'))
)

describe('electron-builder packaging scripts', () => {
  it('finds the packaging scripts to guard', () => {
    // Guard the guard: if the filter matches nothing, the assertions below are vacuous.
    expect(packagingScripts.map(([name]) => name)).toEqual(
      expect.arrayContaining(['build:win', 'build:mac', 'build:linux'])
    )
  })

  it.each(packagingScripts)('%s passes --publish never (no accidental release)', (_name, cmd) => {
    expect(cmd).toContain('--publish never')
  })
})
