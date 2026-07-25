import { readFileSync } from 'fs'
import { resolve } from 'path'
import { describe, it, expect } from 'vitest'

// electron-builder.config.mjs declares a `publish` block (GitHub provider), so
// electron-builder auto-publishes whenever it detects CI — and then dies with
// "GitHub Personal Access Token is not set" in lanes that have no token.
// `build:linux` shipped without the flag and turned the Desktop Windows CI
// Linux job red on main. Every platform build command must pass it.
describe('electron-builder package scripts', () => {
  const scripts = JSON.parse(
    readFileSync(resolve(import.meta.dirname, '../package.json'), 'utf8')
  ).scripts

  const platformBuilds = Object.entries(scripts).filter(
    ([, cmd]) => cmd.includes('electron-builder ') && /\s--(win|mac|linux)\b/.test(cmd)
  )

  it('covers every platform target', () => {
    expect(platformBuilds.map(([name]) => name).sort()).toEqual([
      'build:linux',
      'build:mac',
      'build:win'
    ])
  })

  it.each(platformBuilds)('%s passes --publish never', (_name, cmd) => {
    expect(cmd).toContain('--publish never')
  })
})
