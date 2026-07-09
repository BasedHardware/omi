import { describe, expect, it, vi } from 'vitest'
import type { LocalAgentRuntimeContext, LocalAgentToolDefinition } from '../localAgent/tools'
import {
  buildPiChatRequest,
  chatCompletionsUrl,
  isPiChatEnabled,
  resultToToolContent,
  sendPiChat
} from './chatBridge'

const toolDefinitions = vi.hoisted<LocalAgentToolDefinition[]>(() => [
  {
    name: 'execute_sql',
    description: 'Run read-only SQL.',
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string' } },
      required: ['query'],
      additionalProperties: false
    },
    annotations: {}
  },
  {
    name: 'get_local_status',
    description: 'Read local status.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false
    },
    annotations: {}
  },
  {
    name: 'delete_task',
    description: 'Unavailable mutation.',
    inputSchema: {
      type: 'object',
      properties: { task_id: { type: 'string' } },
      required: ['task_id'],
      additionalProperties: false
    },
    annotations: { destructiveHint: true }
  }
])

vi.mock('../localAgent/tools', () => ({
  listLocalAgentTools: () => toolDefinitions,
  runLocalAgentTool: vi.fn(),
  errorResponseBody: (error: unknown) => ({
    status: 500,
    body: {
      ok: false,
      error: {
        code: 'tool_execution_failed',
        message: error instanceof Error ? error.message : 'Local tool failed'
      }
    }
  })
}))

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body
  } as Response
}

const runtimeContext: LocalAgentRuntimeContext = {
  localUrl: 'omi://local-agent',
  toolEndpoint: 'omi://local-agent/pi-chat-tool',
  app: {
    name: 'Omi Windows',
    version: '1.2.3',
    appId: 'com.omiwindows.app'
  }
}

describe('isPiChatEnabled', () => {
  it('is disabled by default when neither env var is set (fail closed)', () => {
    expect(isPiChatEnabled({})).toBe(false)
  })

  it('stays disabled for explicit off/unknown values', () => {
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: '0' })).toBe(false)
    expect(isPiChatEnabled({ OMI_PI_CHAT: '0' })).toBe(false)
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: '' })).toBe(false)
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: 'false' })).toBe(false)
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: 'banana' })).toBe(false)
  })

  it('enables only when a flag is explicitly truthy', () => {
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: '1' })).toBe(true)
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: 'true' })).toBe(true)
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: 'TRUE' })).toBe(true)
    expect(isPiChatEnabled({ OMI_PI_CHAT: '1' })).toBe(true)
    expect(isPiChatEnabled({ OMI_PI_CHAT: 'yes' })).toBe(true)
  })

  it('does not let one truthy flag be vetoed by the other being off', () => {
    expect(isPiChatEnabled({ OMI_WINDOWS_PI_CHAT: '1', OMI_PI_CHAT: '0' })).toBe(true)
  })

  it('reads process.env by default and fails closed there too', () => {
    const saved = {
      windows: process.env.OMI_WINDOWS_PI_CHAT,
      generic: process.env.OMI_PI_CHAT
    }
    delete process.env.OMI_WINDOWS_PI_CHAT
    delete process.env.OMI_PI_CHAT
    try {
      expect(isPiChatEnabled()).toBe(false)
      process.env.OMI_WINDOWS_PI_CHAT = '1'
      expect(isPiChatEnabled()).toBe(true)
    } finally {
      if (saved.windows === undefined) delete process.env.OMI_WINDOWS_PI_CHAT
      else process.env.OMI_WINDOWS_PI_CHAT = saved.windows
      if (saved.generic === undefined) delete process.env.OMI_PI_CHAT
      else process.env.OMI_PI_CHAT = saved.generic
    }
  })
})

describe('Pi/Omi chat bridge', () => {
  it('constructs OpenAI-compatible omi-provider requests with only allowed local tools', () => {
    const request = buildPiChatRequest([{ role: 'user', content: 'How many screenshots?' }])

    expect(request).toMatchObject({
      model: 'omi-sonnet',
      stream: false,
      tool_choice: 'auto'
    })
    expect(request.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'system' }),
        { role: 'user', content: 'How many screenshots?' }
      ])
    )
    expect(
      (request.tools as { function: { name: string } }[]).map((tool) => tool.function.name)
    ).toEqual(['execute_sql', 'get_local_status'])
  })

  it('fails closed before network use when the Firebase token is missing', async () => {
    const fetchImpl = vi.fn()

    await expect(
      sendPiChat({ token: '   ', messages: [{ role: 'user', content: 'hello' }] }, { fetchImpl })
    ).rejects.toThrow('Firebase ID token')

    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('formats non-JSON local tool results defensively', () => {
    const cyclic: { self?: unknown } = {}
    cyclic.self = cyclic

    expect(resultToToolContent(undefined)).toBe('null')
    expect(resultToToolContent(cyclic)).toBe('[object Object]')
  })

  it('routes model tool calls through the Windows local tool executor', async () => {
    const requests: unknown[] = []
    const fetchImpl = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => {
      requests.push(JSON.parse(String(init.body)))
      if (requests.length === 1) {
        return jsonResponse({
          choices: [
            {
              message: {
                role: 'assistant',
                content: null,
                tool_calls: [
                  {
                    id: 'toolu_1',
                    type: 'function',
                    function: {
                      name: 'execute_sql',
                      arguments: '{"query":"SELECT COUNT(*) AS count FROM rewind_frames"}'
                    }
                  }
                ]
              },
              finish_reason: 'tool_calls'
            }
          ],
          usage: { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 }
        })
      }
      return jsonResponse({
        choices: [
          {
            message: {
              role: 'assistant',
              content: 'You have 3 screenshots.'
            },
            finish_reason: 'stop'
          }
        ],
        usage: { prompt_tokens: 8, completion_tokens: 5, total_tokens: 13 }
      })
    })
    const runTool = vi.fn().mockResolvedValue({
      ok: true,
      name: 'execute_sql',
      content_type: 'application/json',
      result: { columns: ['count'], rows: [{ count: 3 }], row_count: 1 }
    })

    const result = await sendPiChat(
      {
        token: 'firebase-token',
        messages: [{ role: 'user', content: 'How many screenshots do I have?' }]
      },
      {
        fetchImpl,
        runTool,
        toolDefinitions: () => toolDefinitions,
        runtimeContext,
        desktopApiBaseUrl: 'https://desktop.example.test'
      }
    )

    expect(fetchImpl).toHaveBeenCalledWith(
      chatCompletionsUrl('https://desktop.example.test'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          authorization: 'Bearer firebase-token'
        })
      })
    )
    expect(runTool).toHaveBeenCalledWith(
      'execute_sql',
      { query: 'SELECT COUNT(*) AS count FROM rewind_frames' },
      runtimeContext
    )
    expect(
      (requests[1] as { messages: { role: string; tool_call_id?: string }[] }).messages
    ).toEqual(
      expect.arrayContaining([expect.objectContaining({ role: 'tool', tool_call_id: 'toolu_1' })])
    )
    expect(result).toEqual({
      text: 'You have 3 screenshots.',
      toolCalls: [{ id: 'toolu_1', name: 'execute_sql' }],
      usage: { promptTokens: 18, completionTokens: 7, totalTokens: 25 }
    })
  })

  it('serializes unusual local tool results without crashing chat', async () => {
    const requests: unknown[] = []
    const fetchImpl = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => {
      requests.push(JSON.parse(String(init.body)))
      if (requests.length === 1) {
        return jsonResponse({
          choices: [
            {
              message: {
                role: 'assistant',
                content: null,
                tool_calls: [
                  {
                    id: 'toolu_undefined',
                    type: 'function',
                    function: {
                      name: 'get_local_status',
                      arguments: '{}'
                    }
                  }
                ]
              },
              finish_reason: 'tool_calls'
            }
          ]
        })
      }
      return jsonResponse({
        choices: [
          {
            message: {
              role: 'assistant',
              content: 'Handled the tool result.'
            },
            finish_reason: 'stop'
          }
        ]
      })
    })

    const result = await sendPiChat(
      {
        token: 'firebase-token',
        messages: [{ role: 'user', content: 'Check local status' }]
      },
      {
        fetchImpl,
        runTool: vi.fn().mockResolvedValue(undefined),
        toolDefinitions: () => toolDefinitions,
        runtimeContext,
        desktopApiBaseUrl: 'https://desktop.example.test'
      }
    )

    expect((requests[1] as { messages: { role: string; content?: string }[] }).messages).toEqual(
      expect.arrayContaining([expect.objectContaining({ role: 'tool', content: 'null' })])
    )
    expect(result.text).toBe('Handled the tool result.')
  })

  it('rejects model tool calls outside the Pi/Omi chat allowlist before execution', async () => {
    const requests: unknown[] = []
    const fetchImpl = vi.fn().mockImplementation(async (_url: string, init: RequestInit) => {
      requests.push(JSON.parse(String(init.body)))
      if (requests.length === 1) {
        return jsonResponse({
          choices: [
            {
              message: {
                role: 'assistant',
                content: null,
                tool_calls: [
                  {
                    id: 'toolu_delete',
                    type: 'function',
                    function: {
                      name: 'delete_task',
                      arguments: '{"task_id":"task-1"}'
                    }
                  }
                ]
              },
              finish_reason: 'tool_calls'
            }
          ],
          usage: { prompt_tokens: 5, completion_tokens: 1, total_tokens: 6 }
        })
      }
      return jsonResponse({
        choices: [
          {
            message: {
              role: 'assistant',
              content: 'I cannot delete that task from Pi/Omi chat.'
            },
            finish_reason: 'stop'
          }
        ],
        usage: { prompt_tokens: 7, completion_tokens: 8, total_tokens: 15 }
      })
    })
    const runTool = vi.fn()

    const result = await sendPiChat(
      {
        token: 'firebase-token',
        messages: [{ role: 'user', content: 'Delete task task-1' }]
      },
      {
        fetchImpl,
        runTool,
        toolDefinitions: () => toolDefinitions,
        runtimeContext,
        desktopApiBaseUrl: 'https://desktop.example.test'
      }
    )

    expect(runTool).not.toHaveBeenCalled()
    expect((requests[1] as { messages: { role: string; content?: string }[] }).messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'tool',
          content: expect.stringContaining('Tool delete_task not found')
        })
      ])
    )
    expect(result).toMatchObject({
      text: 'I cannot delete that task from Pi/Omi chat.',
      toolCalls: [{ id: 'toolu_delete', name: 'delete_task' }]
    })
  })
})
