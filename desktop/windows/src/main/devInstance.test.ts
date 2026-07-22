import { describe, expect, it } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  computeDevInstance,
  deriveRendererPort,
  deriveCdpPort,
  findWorktreeContext,
  sanitizeInstanceName,
  DEV_RENDERER_BASE,
  DEV_RENDERER_SPAN,
  DEV_CDP_BASE,
  DEV_CDP_SPAN,
  PRIMARY_RENDERER_PORT,
  PRIMARY_CDP_PORT
} from './devInstance'

describe('deriveRendererPort / deriveCdpPort', () => {
  it('are deterministic for the same name', () => {
    expect(deriveRendererPort('multi-worktree-dev')).toBe(deriveRendererPort('multi-worktree-dev'))
    expect(deriveCdpPort('multi-worktree-dev')).toBe(deriveCdpPort('multi-worktree-dev'))
  })

  it('stay within their bands and never hit the primary ports', () => {
    for (let i = 0; i < 200; i++) {
      const name = `worktree-${i}`
      const rp = deriveRendererPort(name)
      const cp = deriveCdpPort(name)
      expect(rp).toBeGreaterThanOrEqual(DEV_RENDERER_BASE)
      expect(rp).toBeLessThan(DEV_RENDERER_BASE + DEV_RENDERER_SPAN)
      expect(rp).not.toBe(PRIMARY_RENDERER_PORT)
      expect(cp).toBeGreaterThanOrEqual(DEV_CDP_BASE)
      expect(cp).toBeLessThan(DEV_CDP_BASE + DEV_CDP_SPAN)
      expect(cp).not.toBe(PRIMARY_CDP_PORT)
    }
  })

  it('disperses distinct worktree names across the renderer band', () => {
    const ports = new Set<number>()
    for (let i = 0; i < 40; i++) ports.add(deriveRendererPort(`feat-branch-${i}`))
    // 40 names into 100 slots: a few collisions are expected (birthday paradox),
    // but the spread must be strong — a broken hash would clump.
    expect(ports.size).toBeGreaterThan(30)
  })

  it('renderer and cdp ports decorrelate for the same name (salting works)', () => {
    // Without the 'cdp:' salt both bands would share the same low-bit offset,
    // so the two offsets-within-band would always match. They must not.
    let sameOffset = 0
    for (let i = 0; i < 100; i++) {
      const name = `wt-${i}`
      if (deriveRendererPort(name) - DEV_RENDERER_BASE === deriveCdpPort(name) - DEV_CDP_BASE) {
        sameOffset++
      }
    }
    // Random chance of a matching offset is ~1/100 each; a handful is fine, but a
    // correlated (unsalted) hash would match ~100/100.
    expect(sameOffset).toBeLessThan(10)
  })
})

describe('sanitizeInstanceName', () => {
  it('lowercases and slugifies, stripping edge dashes', () => {
    expect(sanitizeInstanceName('Feat/My Branch!')).toBe('feat-my-branch')
    expect(sanitizeInstanceName('  UPPER_case.1  ')).toBe('upper_case.1')
  })
  it('never yields an empty string', () => {
    expect(sanitizeInstanceName('///')).toBe('wt')
    expect(sanitizeInstanceName('')).toBe('wt')
  })
})

describe('computeDevInstance', () => {
  it('primary checkout keeps the canonical ports and no title suffix', () => {
    const inst = computeDevInstance('omi', true, {})
    expect(inst).toEqual({
      name: 'primary',
      isPrimary: true,
      rendererPort: PRIMARY_RENDERER_PORT,
      cdpPort: PRIMARY_CDP_PORT,
      titleSuffix: ''
    })
  })

  it('linked worktree derives ports from the folder name and gets a title suffix', () => {
    const inst = computeDevInstance('multi-worktree-dev', false, {})
    expect(inst.isPrimary).toBe(false)
    expect(inst.name).toBe('multi-worktree-dev')
    expect(inst.rendererPort).toBe(deriveRendererPort('multi-worktree-dev'))
    expect(inst.cdpPort).toBe(deriveCdpPort('multi-worktree-dev'))
    expect(inst.titleSuffix).toBe(' — multi-worktree-dev')
  })

  it('OMI_INSTANCE=primary forces primary even from a linked worktree', () => {
    const inst = computeDevInstance('some-worktree', false, { OMI_INSTANCE: 'primary' })
    expect(inst.isPrimary).toBe(true)
    expect(inst.rendererPort).toBe(PRIMARY_RENDERER_PORT)
  })

  it('OMI_INSTANCE=<name> forces a named instance even from the primary checkout', () => {
    const inst = computeDevInstance('omi', true, { OMI_INSTANCE: 'my-exp' })
    expect(inst.isPrimary).toBe(false)
    expect(inst.name).toBe('my-exp')
    expect(inst.rendererPort).toBe(deriveRendererPort('my-exp'))
  })

  it('OMI_DEV_PORT / OMI_DEV_CDP_PORT override the derived ports', () => {
    const inst = computeDevInstance('wt', false, { OMI_DEV_PORT: '5210', OMI_DEV_CDP_PORT: '9250' })
    expect(inst.rendererPort).toBe(5210)
    expect(inst.cdpPort).toBe(9250)
  })

  it('ignores out-of-range / garbage port overrides and falls back to derived', () => {
    const inst = computeDevInstance('wt', false, { OMI_DEV_PORT: '70000', OMI_DEV_CDP_PORT: 'abc' })
    expect(inst.rendererPort).toBe(deriveRendererPort('wt'))
    expect(inst.cdpPort).toBe(deriveCdpPort('wt'))
  })

  it('OMI_DEV_REMOTE_DEBUG wins over OMI_DEV_CDP_PORT for the CDP port', () => {
    // OMI_DEV_REMOTE_DEBUG is the switch dev/bench.ts actually binds, so it must
    // take precedence — otherwise seed-auth would target the wrong port.
    const inst = computeDevInstance('wt', false, {
      OMI_DEV_CDP_PORT: '9251',
      OMI_DEV_REMOTE_DEBUG: '9333'
    })
    expect(inst.cdpPort).toBe(9333)
    // Falls through to OMI_DEV_CDP_PORT when OMI_DEV_REMOTE_DEBUG is garbage.
    const inst2 = computeDevInstance('wt', false, {
      OMI_DEV_CDP_PORT: '9251',
      OMI_DEV_REMOTE_DEBUG: 'nope'
    })
    expect(inst2.cdpPort).toBe(9251)
  })
})

describe('findWorktreeContext', () => {
  it('classifies a .git DIRECTORY as the primary checkout', () => {
    const root = mkdtempSync(join(tmpdir(), 'omi-wt-primary-'))
    try {
      mkdirSync(join(root, '.git'))
      const nested = join(root, 'desktop', 'windows')
      mkdirSync(nested, { recursive: true })
      const ctx = findWorktreeContext(nested)
      expect(ctx.isPrimary).toBe(true)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('classifies a .git FILE (gitdir pointer) as a linked worktree and names it by folder', () => {
    const parent = mkdtempSync(join(tmpdir(), 'omi-wt-linked-'))
    try {
      const wt = join(parent, 'my-feature')
      const nested = join(wt, 'desktop', 'windows')
      mkdirSync(nested, { recursive: true })
      writeFileSync(join(wt, '.git'), 'gitdir: /somewhere/.git/worktrees/my-feature\n')
      const ctx = findWorktreeContext(nested)
      expect(ctx.isPrimary).toBe(false)
      expect(ctx.name).toBe('my-feature')
    } finally {
      rmSync(parent, { recursive: true, force: true })
    }
  })

  it('recovers a linked worktree whose .git pointer was deleted (Windows worktree bug)', () => {
    // A linked worktree nested at <primary>/.worktrees/<name>. Simulate the known
    // Windows bug where the worktree's `.git` pointer FILE vanishes: the walk then
    // reaches the parent primary's `.git` DIRECTORY. It must NOT misdetect as
    // primary (which would bind 5179 + the default profile and clobber the real
    // session) — it recovers the linked identity from the `.worktrees/<name>` path.
    const primary = mkdtempSync(join(tmpdir(), 'omi-wt-orphan-'))
    try {
      mkdirSync(join(primary, '.git')) // primary root: .git DIRECTORY
      const nested = join(primary, '.worktrees', 'my-feature', 'desktop', 'windows')
      mkdirSync(nested, { recursive: true })
      // NOTE: intentionally no `.git` file at the worktree root (deleted).
      const ctx = findWorktreeContext(nested)
      expect(ctx.isPrimary).toBe(false)
      expect(ctx.name).toBe('my-feature')
    } finally {
      rmSync(primary, { recursive: true, force: true })
    }
  })

  it('a real primary checkout (no .worktrees on the path) still classifies as primary', () => {
    const root = mkdtempSync(join(tmpdir(), 'omi-wt-realprimary-'))
    try {
      mkdirSync(join(root, '.git'))
      const nested = join(root, 'desktop', 'windows')
      mkdirSync(nested, { recursive: true })
      expect(findWorktreeContext(nested).isPrimary).toBe(true)
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('falls back to primary when no .git is found', () => {
    const root = mkdtempSync(join(tmpdir(), 'omi-wt-none-'))
    try {
      const ctx = findWorktreeContext(root)
      expect(ctx).toEqual({ name: 'primary', isPrimary: true })
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
})
