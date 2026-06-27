import { beforeEach, describe, expect, it, vi } from 'vitest'
import { gatherLocalContext } from './localAgent'
import type {
  LocalAgentChatToolName,
  LocalAgentChatToolResponse,
  LocalAgentToolArguments
} from '../../../shared/types'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  trackEvent: vi.fn()
}))

vi.mock('./apiClient', () => ({
  desktopApi: {
    post: mocks.post
  }
}))

vi.mock('./analytics', () => ({
  trackEvent: mocks.trackEvent
}))

function localStatus(): LocalAgentChatToolResponse {
  return {
    ok: true,
    name: 'get_local_status',
    content_type: 'application/json',
    result: {
      screenshot_count: 12,
      indexed_screenshot_count: 10,
      latest_capture_at: '2026-06-20T14:00:00.000Z',
      knowledge_graph: { nodeCount: 2, edgeCount: 1 },
      file_index: { filesIndexed: 7 },
      unavailable_affordances: [{ tool: 'delete_task' }]
    }
  }
}

function finalAction(): unknown {
  return { data: { choices: [{ message: { content: '{"action":"final"}' } }] } }
}

function sqlAction(query: string): unknown {
  return {
    data: {
      choices: [
        { message: { content: JSON.stringify({ action: 'execute_sql', input: { query } }) } }
      ]
    }
  }
}

function installWindowMock(
  tool: (
    name: LocalAgentChatToolName,
    args?: LocalAgentToolArguments
  ) => Promise<LocalAgentChatToolResponse>
): void {
  vi.stubGlobal('window', {
    omi: {
      kgQueryNodes: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
      localAgentChatTool: vi.fn(tool)
    }
  })
}

describe('gatherLocalContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.post.mockResolvedValue(finalAction())
  })

  it('adds Rewind screen-history context for earlier-screen questions', async () => {
    installWindowMock(async (name) => {
      if (name === 'get_local_status') return localStatus()
      if (name === 'search_screen_history') {
        return {
          ok: true,
          name,
          content_type: 'application/json',
          result: {
            result_count: 1,
            results: [
              {
                app: 'Code.exe',
                window_title: 'Quarterly roadmap.md',
                start_at: '2026-06-20T13:45:00.000Z',
                match_snippet: 'Quarterly roadmap and launch notes',
                representative: {
                  screenshot_id: 42,
                  timestamp: '2026-06-20T13:45:00.000Z',
                  app: 'Code.exe',
                  window_title: 'Quarterly roadmap.md',
                  ocr_preview: 'Quarterly roadmap'
                },
                screenshots: []
              }
            ]
          }
        }
      }
      if (name === 'get_screenshot') {
        return {
          ok: true,
          name,
          content_type: 'image/jpeg',
          result: {
            screenshot_id: 42,
            image_base64: 'SECRET_SCREENSHOT_BASE64',
            image_mime_type: 'image/jpeg',
            metadata: {
              screenshot_id: 42,
              timestamp: '2026-06-20T13:45:00.000Z',
              app: 'Code.exe',
              window_title: 'Quarterly roadmap.md',
              image_mime_type: 'image/jpeg',
              image_bytes: 1234,
              ocr_preview: 'Quarterly roadmap and launch notes'
            }
          }
        }
      }
      return {
        ok: true,
        name,
        content_type: 'application/json',
        result: {
          columns: ['screenshot_id', 'captured_at_utc', 'app', 'window_title', 'ocr_preview'],
          rows: [
            {
              screenshot_id: 42,
              captured_at_utc: '2026-06-20 13:45:00',
              app: 'Code.exe',
              window_title: 'Quarterly roadmap.md',
              ocr_preview: 'Quarterly roadmap and launch notes'
            }
          ],
          row_count: 1,
          truncated: false
        }
      }
    })

    const out = await gatherLocalContext('what was I looking at earlier?')

    expect(out).toContain('Screen history results')
    expect(out).toContain('Quarterly roadmap.md')
    expect(out).toContain('Screenshot metadata')
    expect(out).toContain('screenshot_id | captured_at_utc')
    expect(out).not.toContain('SECRET_SCREENSHOT_BASE64')
    expect(mocks.trackEvent).toHaveBeenCalledWith(
      'Windows Chat Local Tool Used',
      expect.objectContaining({ tool: 'search_screen_history', ok: true, result_count: 1 })
    )
  })

  it('answers simple local DB count questions through read-only SQL context', async () => {
    installWindowMock(async (name, args) => {
      if (name === 'get_local_status') return localStatus()
      expect(name).toBe('execute_sql')
      expect(String(args?.query)).toContain('local_conversation')
      expect(String(args?.query)).toContain('COUNT(*)')
      return {
        ok: true,
        name,
        content_type: 'application/json',
        result: {
          columns: ['kind', 'count'],
          rows: [{ kind: 'chat', count: 3 }],
          row_count: 1,
          truncated: false
        }
      }
    })

    const out = await gatherLocalContext('how many local chats do I have?')

    expect(out).toContain('Local database result (read-only SQL)')
    expect(out).toContain('kind | count')
    expect(out).toContain('chat | 3')
  })

  it('lets the bounded loop use read-only SQL through the local tool allowlist', async () => {
    mocks.post.mockResolvedValueOnce(sqlAction('SELECT COUNT(*) AS total FROM indexed_files'))
    mocks.post.mockResolvedValueOnce(finalAction())
    installWindowMock(async (name, args) => {
      if (name === 'get_local_status') return localStatus()
      expect(name).toBe('execute_sql')
      expect(args).toEqual({ query: 'SELECT COUNT(*) AS total FROM indexed_files' })
      return {
        ok: true,
        name,
        content_type: 'application/json',
        result: {
          columns: ['total'],
          rows: [{ total: 7 }],
          row_count: 1,
          truncated: false
        }
      }
    })

    const out = await gatherLocalContext('inspect the indexed file table exactly')

    expect(out).toContain('- total')
    expect(out).toContain('- 7')
    expect(mocks.trackEvent).toHaveBeenCalledWith(
      'Windows Chat Local Tool Used',
      expect.objectContaining({ tool: 'execute_sql', ok: true, row_count: 1 })
    )
  })
})
