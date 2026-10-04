// Static coverage ratchet — the shared transport owns the proxy URL and the
// bounded attribution headers; per-owner lane declarations are pinned because
// renderer callers inject their own generate/fetch seams. The compile-time
// assertions live in src/main/assistants/modelPins.test.ts so `pnpm typecheck`
// covers them (src/shared is outside the node tsconfig's include roots).
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { GEMINI_WORKLOADS, GeminiLane } from './geminiAttribution'
import { geminiClientPlatform, geminiProxyFetch, type GeminiProxyRequest } from './geminiProxy'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(HERE, '..')
const REPO_ROOT = resolve(SRC, '..', '..', '..')

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (p.endsWith('.ts') || p.endsWith('.tsx')) yield p
  }
}

describe('geminiProxyFetch — transport contract', () => {
  it('builds the proxy URL and sends the full bounded header set, body, and signal', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }))
    const signal = new AbortController().signal
    const req: GeminiProxyRequest = {
      baseURL: 'https://api.example.test',
      model: 'gemini-2.5-flash',
      action: 'generateContent',
      token: 'tok-1',
      body: '{"contents":[]}',
      lane: GeminiLane.focus,
      workload: 'extraction',
      platform: 'windows',
      signal
    }
    await geminiProxyFetch(fetchImpl, req)
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(
      'https://api.example.test/v1/proxy/gemini/models/gemini-2.5-flash:generateContent'
    )
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer tok-1',
      'X-Omi-Lane': 'focus',
      'X-Omi-Workload': 'extraction',
      'X-Omi-Client-Platform': 'windows'
    })
    expect(init.headers).not.toHaveProperty('X-App-Platform')
    expect(init.body).toBe('{"contents":[]}')
    expect(init.signal).toBe(signal)
  })

  it('routes embedding actions through the same path', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }))
    await geminiProxyFetch(fetchImpl, {
      baseURL: 'b',
      model: 'gemini-embedding-001',
      action: 'batchEmbedContents',
      token: 't',
      body: '{}',
      lane: GeminiLane.embedding,
      workload: 'maintenance',
      platform: 'linux'
    })
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('b/v1/proxy/gemini/models/gemini-embedding-001:batchEmbedContents')
    expect((init.headers as Record<string, string>)['X-Omi-Lane']).toBe('embedding')
  })

  it('selects the streaming proxy route for streamGenerateContent', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }))
    await geminiProxyFetch(fetchImpl, {
      baseURL: 'https://api.example.test',
      model: 'gemini-2.5-flash',
      action: 'streamGenerateContent',
      token: 't',
      body: '{}',
      lane: GeminiLane.focus,
      workload: 'interactive',
      platform: 'windows'
    })
    const [url] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(
      'https://api.example.test/v1/proxy/gemini-stream/models/gemini-2.5-flash:streamGenerateContent'
    )
  })
})

describe('geminiClientPlatform', () => {
  it('maps process.platform to the wire value', () => {
    expect(geminiClientPlatform('win32')).toBe('windows')
    expect(geminiClientPlatform('darwin')).toBe('macos')
    expect(geminiClientPlatform('linux')).toBe('linux')
    expect(geminiClientPlatform('freebsd')).toBe('unknown')
    expect(geminiClientPlatform(undefined)).toBe('unknown')
  })

  it('never emits a value the backend platform resolver does not recognize as a known client (unknown is its fallback)', () => {
    for (const platform of ['win32', 'darwin', 'linux', 'sunos', 'aix', 'freebsd', '']) {
      expect(['windows', 'macos', 'linux', 'unknown']).toContain(geminiClientPlatform(platform))
    }
    expect(['windows', 'macos', 'linux', 'unknown']).toContain(geminiClientPlatform(undefined))
  })
})

describe('canonical attribution contract', () => {
  const canonical = JSON.parse(
    readFileSync(join(REPO_ROOT, 'backend/config/desktop_gemini_attribution.json'), 'utf8')
  ) as { lanes: Record<string, string>; workloads: string[]; platforms: string[] }

  it('generated GeminiLane matches the canonical JSON exactly', () => {
    expect(GeminiLane).toEqual(canonical.lanes)
  })

  it('generated workloads match the canonical JSON exactly', () => {
    expect([...GEMINI_WORKLOADS]).toEqual(canonical.workloads)
  })

  it('every client-emitted platform value is bounded by the contract', () => {
    for (const p of ['windows', 'macos', 'unknown'] as const) {
      expect(canonical.platforms).toContain(p)
    }
    expect(canonical.platforms).toContain('other')
  })


})

describe('transport ownership ratchet', () => {
  const OWNER = 'shared/geminiProxy.ts'

  it('no file outside the shared transport constructs a proxy URL or sets attribution headers', () => {
    const offenders: string[] = []
    for (const file of walk(SRC)) {
      // `join`/`fileURLToPath` yield platform separators; the ratchet compares
      // against forward-slash literals, so normalize once up front.
      const rel = file.slice(SRC.length + 1).split(sep).join('/')
      if (rel === OWNER || rel === 'shared/geminiAttribution.ts' || rel.endsWith('.test.ts'))
        continue
      const src = readFileSync(file, 'utf8')
      if (
        src.includes('proxy/gemini') ||
        src.includes('X-Omi-Lane') ||
        src.includes('X-Omi-Workload')
      ) {
        offenders.push(rel)
      }
    }
    expect(offenders).toEqual([])
  })

  it('every transport owner routes through geminiProxyFetch with a generated lane', () => {
    const owners: [string, string][] = [
      ['main/assistants/focus/gemini.ts', 'GeminiLane.focus'],
      ['main/assistants/memory/gemini.ts', 'GeminiLane.memory'],
      ['main/assistants/goals/generate.ts', 'GeminiLane.goals'],
      ['main/assistants/tasks/geminiWire.ts', 'GeminiLane.taskExtraction'],
      ['main/rewind/embeddingClient.ts', 'GeminiLane.embedding'],
      ['renderer/src/lib/screenSynthesis.ts', 'GeminiLane.screenSynthesis'],
      ['renderer/src/lib/liveNotes/liveNotesMonitor.ts', 'GeminiLane.liveNotes']
    ]
    for (const [rel, lane] of owners) {
      const src = readFileSync(join(SRC, rel), 'utf8')
      expect(src, `${rel} must declare ${lane}`).toContain(lane)
      if (!rel.startsWith('renderer/')) {
        expect(src, `${rel} must use geminiProxyFetch`).toContain('geminiProxyFetch(')
      }
    }
    const rendererClient = readFileSync(join(SRC, 'renderer/src/lib/geminiClient.ts'), 'utf8')
    expect(rendererClient).toContain('geminiProxyFetch(')
  })
})
