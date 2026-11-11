import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { afterEach, describe, expect, it } from 'vitest'
import {
  assertEvidenceFileName,
  assertEvidenceOutRel,
  assertSlug,
  captureEvidence,
  evidenceFileName,
  formatOrdinal,
  hashForRoute,
  mergeEvidence,
  nextOrdinal,
  serializeEvidence,
  upsertEvidence
} from '../e2e/helpers/capture-helpers.mjs'

const roots = []

function makeDir() {
  const root = mkdtempSync(join(tmpdir(), 'omi-capture-evidence-'))
  roots.push(root)
  return root
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

const homeFile = '001-desktop-windows-home.png'
const homeEntry = {
  file: homeFile,
  platform: 'desktop-windows',
  description: 'Home',
  captured_by: 'agent',
  source: 'playwright-e2e'
}

describe('evidence filenames', () => {
  it('pads ordinals and builds the desktop-windows filename', () => {
    expect(formatOrdinal(1)).toBe('001')
    expect(formatOrdinal('7')).toBe('007')
    expect(formatOrdinal('001')).toBe('001')
    expect(evidenceFileName(1, 'settings-home')).toBe('001-desktop-windows-settings-home.png')
    expect(evidenceFileName(42, 'a')).toBe('042-desktop-windows-a.png')
  })

  it('accepts a 40-character slug and rejects a longer one', () => {
    const max = 'a'.repeat(40)
    expect(assertSlug(max)).toBe(max)
    expect(evidenceFileName(1, max)).toBe(`001-desktop-windows-${max}.png`)
    expect(() => assertSlug('a'.repeat(41))).toThrow(/40/)
    expect(() => evidenceFileName(1, 'a'.repeat(41))).toThrow(/40/)
  })

  it('rejects ordinals outside 001-999 and slugs that are not lowercase kebab-case', () => {
    for (const bad of [0, '000', 1000, '1.5', '', '01a', -1]) {
      expect(() => formatOrdinal(bad)).toThrow(/ordinal/)
    }
    for (const bad of ['Home', 'a_b', 'a--b', '-ab', 'ab-', 'a b', '', 'a.b']) {
      expect(() => assertSlug(bad)).toThrow(/slug/)
    }
  })

  it('accepts only <NNN>-desktop-windows-<slug>.png', () => {
    expect(assertEvidenceFileName(homeFile)).toEqual({ ordinal: 1, slug: 'home', file: homeFile })
    expect(assertEvidenceFileName('999-desktop-windows-chat-home.png').slug).toBe('chat-home')
    for (const bad of [
      '000-desktop-windows-home.png',
      '01-desktop-windows-home.png',
      '1000-desktop-windows-home.png',
      '001-desktop-macos-home.png',
      '001-desktop-windows-Home.png',
      '001-desktop-windows-.png',
      '001-desktop-windows-a--b.png',
      `001-desktop-windows-${'a'.repeat(41)}.png`,
      '001-desktop-windows-home.png.bak',
      '001-desktop-windows-../x.png',
      'home.png'
    ]) {
      expect(() => assertEvidenceFileName(bad)).toThrow(/filename/)
    }
  })
})

describe('evidence.json merge', () => {
  it('creates a version-1 manifest with the contract field order', () => {
    expect(mergeEvidence(null, { file: homeFile, description: 'Home' })).toEqual({
      version: 1,
      images: [homeEntry]
    })
  })

  it('serializes with 2-space indent and a trailing newline', () => {
    const text = serializeEvidence(mergeEvidence(null, { file: homeFile, description: 'Home' }))
    expect(text).toBe(`${JSON.stringify({ version: 1, images: [homeEntry] }, null, 2)}\n`)
    expect(text.endsWith('\n')).toBe(true)
    expect(text.endsWith('\n\n')).toBe(false)
  })

  it('appends a new file and replaces an existing one in place', () => {
    const macos = {
      file: '001-desktop-macos-chat.png',
      platform: 'desktop-macos',
      description: 'Chat',
      captured_by: 'human',
      source: 'manual'
    }
    const web = {
      file: '003-web-login.png',
      platform: 'web',
      description: 'Login',
      captured_by: 'agent',
      source: 'visual-audit'
    }
    const existing = {
      version: 1,
      images: [
        macos,
        { ...homeEntry, file: '002-desktop-windows-home.png', description: 'Old' },
        web
      ]
    }
    const replaced = '002-desktop-windows-home.png'
    const next = mergeEvidence(existing, { file: replaced, description: 'Home refreshed' })
    expect(next.images.map((item) => item.file)).toEqual([macos.file, replaced, web.file])
    expect(next.images[0]).toEqual(macos)
    expect(next.images[1]).toEqual({ ...homeEntry, file: replaced, description: 'Home refreshed' })
    expect(next.images[2]).toEqual(web)

    const appended = mergeEvidence(next, {
      file: '004-desktop-windows-settings.png',
      description: 'Settings'
    })
    expect(appended.images).toHaveLength(4)
    expect(appended.images[3].file).toBe('004-desktop-windows-settings.png')
    expect(appended.images[1].description).toBe('Home refreshed')
  })

  it('collapses duplicate file names to one entry', () => {
    const existing = {
      version: 1,
      images: [
        { ...homeEntry, description: 'First' },
        { file: '002-desktop-windows-tasks.png', description: 'Tasks' },
        { ...homeEntry, description: 'Duplicate' }
      ]
    }
    const next = mergeEvidence(existing, { file: homeFile, description: 'Home' })
    expect(next.images.map((item) => item.file)).toEqual([
      homeFile,
      '002-desktop-windows-tasks.png'
    ])
    expect(next.images[0].description).toBe('Home')
  })

  it('preserves unrelated top-level keys and rejects a bad manifest', () => {
    const next = mergeEvidence(
      { note: 'keep', version: 1, images: [] },
      { file: homeFile, description: 'Home' }
    )
    expect(next.note).toBe('keep')
    expect(next.version).toBe(1)
    expect(() =>
      mergeEvidence({ version: 2, images: [] }, { file: homeFile, description: 'Home' })
    ).toThrow(/version/)
    expect(() => mergeEvidence({ version: 1 }, { file: homeFile, description: 'Home' })).toThrow(
      /images/
    )
    expect(() => mergeEvidence(null, { file: homeFile, description: '   ' })).toThrow(/description/)
    expect(() =>
      mergeEvidence(null, { file: homeFile, description: 'Home', platform: 'web' })
    ).toThrow(/platform/)
  })

  it('round-trips evidence.json from a temp directory without duplicating', () => {
    const dir = makeDir()
    upsertEvidence(dir, { file: homeFile, description: 'Home' })
    upsertEvidence(dir, { file: homeFile, description: 'Home again' })
    upsertEvidence(dir, { file: '002-desktop-windows-settings.png', description: 'Settings' })
    const raw = readFileSync(join(dir, 'evidence.json'), 'utf8')
    expect(raw.endsWith('\n')).toBe(true)
    const doc = JSON.parse(raw)
    expect(doc.images).toHaveLength(2)
    expect(doc.images[0].description).toBe('Home again')
    expect(doc.images[1].file).toBe('002-desktop-windows-settings.png')
    expect(nextOrdinal(doc)).toBe(3)
    expect(nextOrdinal(null)).toBe(1)
  })

  it('refuses to merge into invalid JSON', () => {
    const dir = makeDir()
    writeFileSync(join(dir, 'evidence.json'), '{')
    expect(() => upsertEvidence(dir, { file: homeFile, description: 'Home' })).toThrow(
      /not valid JSON/
    )
  })

  it('picks the next ordinal after every platform, skipping 000', () => {
    expect(
      nextOrdinal({
        version: 1,
        images: [
          { file: '001-desktop-macos-chat.png' },
          { file: '000-desktop-windows-nope.png' },
          { file: '009-web-login.png' },
          { file: 'notes.txt' }
        ]
      })
    ).toBe(10)
    expect(() => nextOrdinal({ images: [{ file: '999-desktop-windows-home.png' }] })).toThrow(/999/)
  })
})

describe('evidence output path and routes', () => {
  it('accepts a repo-relative silo directory and rejects escapes', () => {
    expect(assertEvidenceOutRel('.agent-artifacts/ui-evidence/20882')).toBe(
      '.agent-artifacts/ui-evidence/20882'
    )
    expect(assertEvidenceOutRel('.agent-artifacts/ui-evidence/lane-ui-screenshot-gate/')).toBe(
      '.agent-artifacts/ui-evidence/lane-ui-screenshot-gate'
    )
    for (const bad of [
      '.agent-artifacts/ui-evidence/Lane',
      '.agent-artifacts/ui-evidence/a/b',
      '.agent-artifacts/ui-evidence/../secrets',
      '/tmp/ui-evidence/home',
      'desktop/windows/.agent-artifacts/ui-evidence/home',
      ''
    ]) {
      expect(() => assertEvidenceOutRel(bad)).toThrow(/--out/)
    }
  })

  it('normalizes hash routes the renderer already serves', () => {
    expect(hashForRoute('settings')).toBe('#/settings')
    expect(hashForRoute('/settings')).toBe('#/settings')
    expect(hashForRoute('#/conversations/live?x=1')).toBe('#/conversations/live')
    expect(hashForRoute('bar')).toBe('#/bar')
    expect(() => hashForRoute('../etc')).toThrow(/route/)
    expect(() => hashForRoute('#settings')).toThrow(/route/)
  })
})

describe('captureEvidence', () => {
  it('writes the png path and upserts the manifest without reading pixels', async () => {
    const dir = makeDir()
    const page = {
      async screenshot({ path: dest }) {
        writeFileSync(dest, Buffer.from('not-a-real-png'))
      }
    }
    const result = await captureEvidence(page, {
      slug: 'settings-home',
      ordinal: 1,
      describe: 'Settings home',
      outDir: dir
    })
    expect(result.file).toBe('001-desktop-windows-settings-home.png')
    expect(readFileSync(result.path, 'utf8')).toBe('not-a-real-png')
    const raw = readFileSync(join(dir, 'evidence.json'), 'utf8')
    expect(JSON.parse(raw)).toEqual({
      version: 1,
      images: [
        {
          file: '001-desktop-windows-settings-home.png',
          platform: 'desktop-windows',
          description: 'Settings home',
          captured_by: 'agent',
          source: 'playwright-e2e'
        }
      ]
    })
    expect(raw.endsWith('\n')).toBe(true)

    await captureEvidence(page, {
      slug: 'settings-home',
      ordinal: 1,
      describe: 'Settings home again',
      outDir: dir
    })
    const again = JSON.parse(readFileSync(join(dir, 'evidence.json'), 'utf8'))
    expect(again.images).toHaveLength(1)
    expect(again.images[0].description).toBe('Settings home again')
  })

  it('does not screenshot when the filename would violate the contract', async () => {
    const dir = makeDir()
    let shots = 0
    const page = {
      async screenshot() {
        shots++
      }
    }
    await expect(captureEvidence(page, { slug: 'Nope', ordinal: 1, outDir: dir })).rejects.toThrow(
      /slug/
    )
    await expect(
      captureEvidence(page, { slug: 'home', ordinal: 1, describe: '   ', outDir: dir })
    ).rejects.toThrow(/description/)
    expect(shots).toBe(0)
  })

  it('defaults the description to the slug', async () => {
    const dir = makeDir()
    const page = {
      async screenshot({ path: dest }) {
        writeFileSync(dest, Buffer.from('x'))
      }
    }
    const result = await captureEvidence(page, { slug: 'home', ordinal: 2, outDir: dir })
    expect(result.evidence.images[0].description).toBe('home')
    expect(result.file).toBe('002-desktop-windows-home.png')
  })
})
