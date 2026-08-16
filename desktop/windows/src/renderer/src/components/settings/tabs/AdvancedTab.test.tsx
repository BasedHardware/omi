// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { AdvancedTab } from './AdvancedTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'

// AdvancedTab drives the shared axios `omiApi` instance directly (not the
// generated fetch client) — see apiClient.ts. Stub it so the import-batching
// fix is exercised without a live backend.
const omiApiGet = vi.fn()
const omiApiPost = vi.fn()

vi.mock('../../../lib/apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => omiApiGet(...args),
    post: (...args: unknown[]) => omiApiPost(...args),
    patch: vi.fn(),
    delete: vi.fn()
  },
  desktopApi: { get: vi.fn(), post: vi.fn() }
}))

// extractMemories hits an LLM over desktopApi — stub it directly so the test
// controls exactly which "extracted" list feeds the import step.
const extractMemories = vi.fn()
vi.mock('../../../lib/memoryExtract', () => ({
  extractMemories: (...args: unknown[]) => extractMemories(...args)
}))

// Not under test here — avoid touching the real local-KG pipeline.
vi.mock('../../../lib/kgSynthesis', () => ({ buildLocalGraph: vi.fn() }))

const renderTab = (): void => {
  render(
    <SettingsSearchProvider>
      <AdvancedTab />
    </SettingsSearchProvider>
  )
}

beforeEach(() => {
  omiApiGet.mockReset().mockResolvedValue({ data: [] })
  omiApiPost.mockReset()
  extractMemories.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    indexFilesStatus: vi.fn().mockResolvedValue(null),
    kgStatus: vi.fn().mockResolvedValue(null),
    memoryImportParse: vi.fn().mockResolvedValue([]),
    memoryExportObsidian: vi.fn(),
    memoryExportFile: vi.fn(),
    memoryExportNotion: vi.fn(),
    // AdvancedTab now embeds the BYOK "Developer API Keys" subsection, which
    // reads stored keys on mount (and would enroll/clear on interaction).
    byokGetAll: vi.fn().mockResolvedValue({}),
    byokSet: vi.fn().mockResolvedValue(undefined),
    byokClearAll: vi.fn().mockResolvedValue(undefined),
    byokEnroll: vi.fn().mockResolvedValue({ active: false, results: {} }),
    // AdvancedTab now embeds the AI profile subsection, which reads the latest
    // record on mount.
    aiProfileGetLatest: vi.fn().mockResolvedValue(null),
    aiProfileGenerateNow: vi.fn(),
    aiProfileEdit: vi.fn(),
    aiProfileDelete: vi.fn(),
    // SettingsSearchProvider mounts every settings tab (incl. IntegrationsTab) to
    // index its text; with the Gmail-session flag now ON by default, that tab's
    // mount effect reads the session status. Stub it so the effect resolves cleanly.
    gmailSessionStatus: vi.fn().mockResolvedValue({ connected: false })
  }
})

afterEach(cleanup)

describe('AdvancedTab memory import batching (C8)', () => {
  it('chunks a 250-item import into 3 sequential POST /v3/memories/batch calls of 100/100/50', async () => {
    const items = Array.from({ length: 250 }, (_, i) => `Fact number ${i}`)
    extractMemories.mockResolvedValue({ memories: items, profile: '' })
    omiApiPost.mockResolvedValue({ data: { created_count: 100, memories: [] } })

    renderTab()

    fireEvent.change(screen.getByPlaceholderText(/Paste the assistant/), {
      target: { value: 'a pasted export' }
    })
    fireEvent.click(screen.getByText('Extract memories'))

    const importButton = await screen.findByText('Import 250 memories')
    fireEvent.click(importButton)

    await waitFor(() => expect(omiApiPost).toHaveBeenCalledTimes(3))

    // Every call hits the batch endpoint, never the one-memory-per-POST path.
    for (const call of omiApiPost.mock.calls) {
      expect(call[0]).toBe('/v3/memories/batch')
    }
    expect(omiApiPost.mock.calls[0][1].memories).toHaveLength(100)
    expect(omiApiPost.mock.calls[1][1].memories).toHaveLength(100)
    expect(omiApiPost.mock.calls[2][1].memories).toHaveLength(50)
    // Payload shape matches BatchMemoriesRequest: { memories: [{ content }] }.
    expect(omiApiPost.mock.calls[0][1].memories[0]).toEqual({ content: 'Fact number 0' })
  })

  it('never calls the single-memory POST /v3/memories endpoint during import', async () => {
    const items = Array.from({ length: 5 }, (_, i) => `Fact ${i}`)
    extractMemories.mockResolvedValue({ memories: items, profile: '' })
    omiApiPost.mockResolvedValue({ data: { created_count: 5, memories: [] } })

    renderTab()
    fireEvent.change(screen.getByPlaceholderText(/Paste the assistant/), {
      target: { value: 'a pasted export' }
    })
    fireEvent.click(screen.getByText('Extract memories'))

    const importButton = await screen.findByText('Import 5 memories')
    fireEvent.click(importButton)

    await waitFor(() => expect(omiApiPost).toHaveBeenCalledTimes(1))
    expect(omiApiPost).not.toHaveBeenCalledWith('/v3/memories', expect.anything())
  })
})
