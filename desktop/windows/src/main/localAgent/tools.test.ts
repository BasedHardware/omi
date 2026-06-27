import Database from 'better-sqlite3'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocalConversation, RewindFrame } from '../../shared/types'

const electronState = vi.hoisted(() => ({
  userData: ''
}))

vi.mock('electron', () => ({
  app: {
    getName: (): string => 'Omi Windows',
    getVersion: (): string => '1.2.3',
    getPath: (name: string): string => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`)
      return electronState.userData
    }
  }
}))

const context = {
  localUrl: 'http://127.0.0.1:47778',
  toolEndpoint: 'http://127.0.0.1:47778/v1/local/tool',
  app: {
    name: 'Omi Windows',
    version: '1.2.3',
    appId: 'com.omiwindows.app'
  }
}

async function freshModules(): Promise<{
  tools: typeof import('./tools')
  db: typeof import('../ipc/db')
}> {
  vi.resetModules()
  const tools = await import('./tools')
  const db = await import('../ipc/db')
  return { tools, db }
}

function conversation(over: Partial<LocalConversation> = {}): LocalConversation {
  const now = Date.now()
  return {
    id: 'conversation-1',
    startedAt: now - 1_000,
    endedAt: now,
    transcript: 'Discussed the local agent tool registry.',
    createdAt: now,
    kind: 'recording',
    title: 'Local tools',
    ...over
  }
}

function frame(
  imagePath: string,
  over: Partial<Omit<RewindFrame, 'id'>> = {}
): Omit<RewindFrame, 'id'> {
  return {
    ts: Date.now(),
    app: 'Code.exe',
    windowTitle: 'localAgent tools',
    processName: 'Code',
    ocrText: 'first local agent tool set screen history',
    imagePath,
    width: 1280,
    height: 720,
    indexed: 1,
    ...over
  }
}

describe('local agent tool registry', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-local-agent-tools-'))
    process.env.OMI_DB_PATH = join(electronState.userData, 'omi.db')
  })

  afterEach(() => {
    delete process.env.OMI_DB_PATH
    vi.resetModules()
    rmSync(electronState.userData, { recursive: true, force: true })
    electronState.userData = ''
  })

  it('lists JSON-schema tool definitions with unavailable destructive task annotations', async () => {
    const { tools } = await freshModules()
    const definitions = tools.listLocalAgentTools()

    expect(definitions.map((tool) => tool.name)).toEqual(
      expect.arrayContaining([
        'get_local_status',
        'execute_sql',
        'search_screen_history',
        'semantic_search',
        'get_screenshot',
        'get_daily_recap',
        'search_tasks',
        'complete_task',
        'delete_task'
      ])
    )
    expect(definitions.find((tool) => tool.name === 'execute_sql')).toMatchObject({
      inputSchema: {
        type: 'object',
        required: ['query']
      },
      annotations: {
        readOnlyHint: true,
        readOnlyEnforced: true,
        mutationStatementsRejected: true
      }
    })
    expect(definitions.find((tool) => tool.name === 'delete_task')).toMatchObject({
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        gated: true,
        unavailable: true
      }
    })
  })

  it('runs read-only SQL through the guard and rejects mutations', async () => {
    const { tools, db } = await freshModules()
    db.insertLocalConversation(conversation())

    const result = await tools.runLocalAgentTool(
      'execute_sql',
      { query: 'SELECT id, title FROM local_conversation' },
      context
    )

    expect(result).toMatchObject({
      ok: true,
      name: 'execute_sql',
      result: {
        columns: ['id', 'title'],
        row_count: 1,
        read_only: true,
        max_rows: 200
      }
    })
    expect((result.result as { rows: Record<string, unknown>[] }).rows[0]).toEqual({
      id: 'conversation-1',
      title: 'Local tools'
    })

    await expect(
      tools.runLocalAgentTool('execute_sql', { query: 'DELETE FROM local_conversation' }, context)
    ).rejects.toMatchObject({
      code: 'sql_rejected_or_failed',
      status: 400
    })
  })

  it('searches Rewind history and returns screenshot image data by frame id', async () => {
    const { tools, db } = await freshModules()
    const imagePath = join(electronState.userData, 'rewind', '2026-06-20', 'frame.jpg')
    mkdirSync(dirname(imagePath), { recursive: true })
    const imageBytes = Buffer.from([1, 2, 3, 4])
    writeFileSync(imagePath, imageBytes)
    const id = db.insertRewindFrame(frame(imagePath))

    const search = await tools.runLocalAgentTool(
      'search_screen_history',
      { query: 'agent tool set', days: 1 },
      context
    )
    const searchResult = search.result as {
      result_count: number
      results: { representative: { screenshot_id: number } }[]
    }
    expect(searchResult.result_count).toBe(1)
    expect(searchResult.results[0].representative.screenshot_id).toBe(id)

    const screenshot = await tools.runLocalAgentTool(
      'get_screenshot',
      { screenshot_id: id },
      context
    )
    expect(screenshot).toMatchObject({
      ok: true,
      name: 'get_screenshot',
      content_type: 'image/jpeg',
      result: {
        screenshot_id: id,
        image_base64: imageBytes.toString('base64'),
        metadata: {
          screenshot_id: id,
          app: 'Code.exe',
          window_title: 'localAgent tools'
        }
      }
    })
  })

  it('searches supported local task tables and marks mutations unavailable', async () => {
    const raw = new Database(process.env.OMI_DB_PATH!)
    raw.exec(`
      CREATE TABLE action_items (
        id TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        deleted INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
      );
      INSERT INTO action_items (id, description, completed, deleted, created_at)
      VALUES ('task-1', 'Prepare the local tools demo', 0, 0, ${Date.now()});
      INSERT INTO action_items (id, description, completed, deleted, created_at)
      VALUES ('task-2', 'Completed task', 1, 0, ${Date.now() - 1});
    `)
    raw.close()

    const { tools } = await freshModules()
    const result = await tools.runLocalAgentTool(
      'search_tasks',
      { query: 'local tools', include_completed: false },
      context
    )

    expect(result).toMatchObject({
      ok: true,
      name: 'search_tasks',
      result: {
        available: true,
        sources: ['action_items'],
        result_count: 1,
        tasks: [
          {
            source: 'action_items',
            id: 'task-1',
            description: 'Prepare the local tools demo',
            completed: false
          }
        ]
      }
    })

    await expect(
      tools.runLocalAgentTool('delete_task', { task_id: 'task-1' }, context)
    ).rejects.toMatchObject({
      code: 'tool_unavailable',
      status: 501
    })
  })
})
