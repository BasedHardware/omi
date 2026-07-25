import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { afterEach, describe, expect, it } from 'vitest'
import { checkClaudeBinary, findClaudeBinary } from './claude-binary-check.mjs'

const roots = []

function makeRoot() {
  const root = mkdtempSync(join(tmpdir(), 'omi-claude-binary-check-'))
  roots.push(root)
  return root
}

function writeBinary(dir, bytes) {
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'claude.exe'), Buffer.alloc(bytes, 1))
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('checkClaudeBinary', () => {
  it('skips on non-Windows platforms', () => {
    expect(checkClaudeBinary(makeRoot(), 'darwin')).toEqual({ ok: true, skipped: true })
  })

  it('fails loudly when the optional package is absent (the pnpm-exit-0 case)', () => {
    const result = checkClaudeBinary(makeRoot(), 'win32')
    expect(result.ok).toBe(false)
    expect(result.reason).toContain('optionalDependency')
    expect(result.reason).toContain('pnpm install')
  })

  it('does not mistake an empty residual virtual-store directory for an install', () => {
    // A failed optional download can leave the .pnpm dir behind with no
    // claude.exe inside — the exact shape seen in the PR #9304 review.
    const root = makeRoot()
    mkdirSync(
      join(
        root,
        'node_modules',
        '.pnpm',
        '@anthropic-ai+claude-agent-sdk-win32-x64@0.3.205',
        'node_modules',
        '@anthropic-ai',
        'claude-agent-sdk-win32-x64'
      ),
      { recursive: true }
    )
    const result = checkClaudeBinary(root, 'win32')
    expect(result.ok).toBe(false)
    expect(result.reason).toContain('claude.exe not found')
  })

  it('fails on a truncated download', () => {
    const root = makeRoot()
    writeBinary(join(root, 'node_modules', '@anthropic-ai', 'claude-agent-sdk-win32-x64'), 10)
    const result = checkClaudeBinary(root, 'win32', 1024)
    expect(result.ok).toBe(false)
    expect(result.reason).toContain('truncated')
  })

  it('passes with a plausible binary in the flattened layout', () => {
    const root = makeRoot()
    writeBinary(join(root, 'node_modules', '@anthropic-ai', 'claude-agent-sdk-win32-x64'), 2048)
    const result = checkClaudeBinary(root, 'win32', 1024)
    expect(result.ok).toBe(true)
    expect(result.size).toBe(2048)
  })

  it('finds the binary in the pnpm virtual-store layout too', () => {
    const root = makeRoot()
    writeBinary(
      join(
        root,
        'node_modules',
        '.pnpm',
        '@anthropic-ai+claude-agent-sdk-win32-x64@0.3.205',
        'node_modules',
        '@anthropic-ai',
        'claude-agent-sdk-win32-x64'
      ),
      2048
    )
    expect(findClaudeBinary(root)).toContain('.pnpm')
    expect(checkClaudeBinary(root, 'win32', 1024).ok).toBe(true)
  })
})
