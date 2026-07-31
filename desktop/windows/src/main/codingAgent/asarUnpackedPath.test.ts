// Regression test for the packaged-build agent-spawn failure: the coding-agent
// ACP entry (and the omi MCP entry) were spawned from their `?asset` path INSIDE
// app.asar. A plain-Node child can't exec the SDK's claude.exe from the archive,
// so session/new failed with a bare -32603 "Internal error" ("... claude.exe
// exists but failed to launch"). asarUnpackedEntryPath must redirect a packaged
// app.asar path to its app.asar.unpacked twin.
import { describe, it, expect } from 'vitest'
import { asarUnpackedEntryPath } from './asarUnpackedPath'

const alwaysExists = () => true
const neverExists = () => false

describe('asarUnpackedEntryPath', () => {
  it('redirects a packaged Windows app.asar path to app.asar.unpacked', () => {
    const asar =
      'C:\\Users\\chris\\AppData\\Local\\Programs\\omi-windows\\resources\\app.asar\\out\\main\\chunks\\claude-acp-entry-C0Tl5s5P.mjs'
    expect(asarUnpackedEntryPath(asar, alwaysExists)).toBe(
      'C:\\Users\\chris\\AppData\\Local\\Programs\\omi-windows\\resources\\app.asar.unpacked\\out\\main\\chunks\\claude-acp-entry-C0Tl5s5P.mjs'
    )
  })

  it('redirects a POSIX app.asar path (forward slashes) too', () => {
    const asar = '/Applications/Omi.app/Contents/Resources/app.asar/out/main/chunks/omi-mcp-entry.mjs'
    expect(asarUnpackedEntryPath(asar, alwaysExists)).toBe(
      '/Applications/Omi.app/Contents/Resources/app.asar.unpacked/out/main/chunks/omi-mcp-entry.mjs'
    )
  })

  it('leaves a dev path (no app.asar segment) unchanged', () => {
    const dev = 'C:\\Users\\chris\\projects\\omi\\desktop\\windows\\out\\main\\chunks\\claude-acp-entry.mjs'
    expect(asarUnpackedEntryPath(dev, alwaysExists)).toBe(dev)
  })

  it('does NOT double-rewrite an already-unpacked path', () => {
    const unpacked =
      'C:\\app\\resources\\app.asar.unpacked\\out\\main\\chunks\\claude-acp-entry.mjs'
    expect(asarUnpackedEntryPath(unpacked, alwaysExists)).toBe(unpacked)
  })

  it('falls back to the original when the unpacked twin is absent (misconfigured build)', () => {
    const asar = '/app/resources/app.asar/out/main/chunks/claude-acp-entry.mjs'
    expect(asarUnpackedEntryPath(asar, neverExists)).toBe(asar)
  })
})
