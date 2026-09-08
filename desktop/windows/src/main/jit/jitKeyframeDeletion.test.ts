import { DatabaseSync } from 'node:sqlite'
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SqliteAgentStore, type DatabaseFactory } from '../agentKernel/store'
import { conversationIdsForDeletion } from '../agentKernel/conversationTurns'
import { resolveSurfaceSession } from '../agentKernel/surfaceSession'
import {
  deleteJitKeyframeFileThenReferences,
  drainJitKeyframeCleanup,
  jitConversationIdsForDeletion,
  listJitKeyframePinsForDeletion
} from './jitKeyframeDeletion'
import {
  enqueueJitKeyframeCleanup,
  initializeJitTriggerMirror,
  isJitConversationKeyframePinned,
  listPendingJitKeyframeCleanup,
  pinJitConversationKeyframe,
  type JitMirrorStatement,
  type JitMirrorDb
} from './jitTriggerMirror'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const cleanupDirs: string[] = []

afterEach(() => {
  for (const dir of cleanupDirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

describe('JIT keyframe deletion', () => {
  it('retires a dedicated JIT surface pin through the real renderer deletion key', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'omi-jit-renderer-delete-'))
    cleanupDirs.push(dir)
    const store = new SqliteAgentStore({
      databaseFactory: nodeSqliteFactory,
      databasePath: join(dir, 'agent.sqlite3'),
      reconcileOnOpen: false
    })
    const renderer = resolveSurfaceSession(
      store,
      {
        ownerId: 'owner',
        surfaceRef: {
          surfaceKind: 'main_chat',
          externalRefKind: 'chat',
          externalRefId: 'renderer-chat-42'
        }
      },
      () => 100
    )
    const jit = resolveSurfaceSession(
      store,
      {
        ownerId: 'owner',
        surfaceRef: {
          surfaceKind: 'jit_assistant',
          externalRefKind: 'candidate',
          externalRefId: 'candidate-hash'
        }
      },
      () => 101
    )
    expect(jit.conversationId).not.toBe(renderer.conversationId)

    const db = new DatabaseSync(':memory:')
    initializeJitTriggerMirror(db as unknown as JitMirrorDb)
    db.exec(
      `CREATE TABLE rewind_frames (
        id INTEGER PRIMARY KEY,
        image_path TEXT NOT NULL
      )`
    )
    const imagePath = join(dir, 'frame.jpg')
    writeFileSync(imagePath, 'frame')
    db.prepare('INSERT INTO rewind_frames (id, image_path) VALUES (?, ?)').run(42, imagePath)
    const mirror = db as unknown as JitMirrorDb
    pinJitConversationKeyframe(mirror, {
      frameId: 42,
      ownerId: 'owner',
      conversationId: jit.conversationId,
      imagePath,
      rendererDeletionKey: 'renderer-chat-42',
      pinnedAt: 102
    })

    const pins = listJitKeyframePinsForDeletion(mirror, 'renderer-chat-42', (key) =>
      conversationIdsForDeletion(store, 'owner', key)
    )
    expect(pins.map((pin) => pin.conversationId)).toEqual([jit.conversationId])
    for (const pin of pins) {
      enqueueJitKeyframeCleanup(mirror, pin, 102)
    }
    const removed = await drainJitKeyframeCleanup({
      db: mirror,
      readFrame: (frameId) =>
        db
          .prepare('SELECT image_path AS imagePath FROM rewind_frames WHERE id = ?')
          .get(frameId) as { imagePath: string } | null,
      removeFile: async (path) => rmSync(path),
      deleteFrame: (frameId) => db.prepare('DELETE FROM rewind_frames WHERE id = ?').run(frameId),
      now: () => 102
    })

    expect(removed).toBe(1)
    expect(existsSync(imagePath)).toBe(false)
    expect(db.prepare('SELECT COUNT(*) AS n FROM rewind_frames').get()).toEqual({ n: 0 })
    expect(isJitConversationKeyframePinned(mirror, 42)).toBe(false)
    expect(listPendingJitKeyframeCleanup(mirror, 102)).toHaveLength(0)
    db.close()
    store.close()
  })

  it('maps a renderer chat session to its agent conversation while retaining the session key', () => {
    expect(jitConversationIdsForDeletion('chat-session-1', () => 'agent-conversation-1')).toEqual([
      'chat-session-1',
      'agent-conversation-1'
    ])
  })

  it('can fail closed when an authoritative store resolver has no mapping', () => {
    expect(
      jitConversationIdsForDeletion('renderer-chat-session', () => [], {
        includeOriginalKey: false
      })
    ).toEqual([])
  })

  it('uses the real kernel schema to map a renderer session before JIT cleanup', () => {
    const dir = mkdtempSync(join(tmpdir(), 'omi-jit-delete-'))
    cleanupDirs.push(dir)
    const store = new SqliteAgentStore({
      databaseFactory: nodeSqliteFactory,
      databasePath: join(dir, 'agent.sqlite3'),
      reconcileOnOpen: false
    })
    const resolved = resolveSurfaceSession(
      store,
      {
        ownerId: 'owner',
        surfaceRef: {
          surfaceKind: 'main_chat',
          externalRefKind: 'chat',
          externalRefId: 'real-renderer-session'
        }
      },
      () => 100
    )

    expect(
      jitConversationIdsForDeletion(
        'real-renderer-session',
        (key) => conversationIdsForDeletion(store, 'owner', key),
        { includeOriginalKey: false }
      )
    ).toEqual([resolved.conversationId])
    store.close()
  })

  it('keeps frame and pin references when file deletion fails', async () => {
    const deleteFrame = vi.fn()
    const removePin = vi.fn()
    const result = await deleteJitKeyframeFileThenReferences({
      removeFile: async () => {
        throw Object.assign(new Error('permission denied'), { code: 'EACCES' })
      },
      deleteFrame,
      removePin
    })

    expect(result).toBe('retry')
    expect(deleteFrame).not.toHaveBeenCalled()
    expect(removePin).not.toHaveBeenCalled()
  })

  it.each([
    ['successful delete', undefined],
    ['already absent file', Object.assign(new Error('missing'), { code: 'ENOENT' })]
  ])('%s retires both references', async (_label, error) => {
    const deleteFrame = vi.fn()
    const removePin = vi.fn()
    const result = await deleteJitKeyframeFileThenReferences({
      removeFile: async () => {
        if (error) throw error
      },
      deleteFrame,
      removePin
    })

    expect(result).toBe('removed')
    expect(deleteFrame).toHaveBeenCalledOnce()
    expect(removePin).toHaveBeenCalledOnce()
  })

  it('keeps the durable pin when a missing rewind row still has an unlinkable path', async () => {
    const db = new DatabaseSync(':memory:')
    initializeJitTriggerMirror(db as unknown as JitMirrorDb)
    const mirror = db as unknown as JitMirrorDb
    pinJitConversationKeyframe(mirror, {
      frameId: 7,
      ownerId: 'owner',
      conversationId: 'agent-conversation',
      imagePath: 'C:/rewind/7.jpg'
    })
    enqueueJitKeyframeCleanup(
      mirror,
      {
        frameId: 7,
        ownerId: 'owner',
        conversationId: 'agent-conversation',
        imagePath: 'C:/rewind/7.jpg'
      },
      100
    )
    const removeFile = vi.fn(async () => {
      throw Object.assign(new Error('locked'), { code: 'EACCES' })
    })
    const removed = await drainJitKeyframeCleanup({
      db: mirror,
      readFrame: () => null,
      removeFile,
      deleteFrame: vi.fn(),
      now: () => 100
    })
    expect(removed).toBe(0)
    expect(removeFile).toHaveBeenCalledWith('C:/rewind/7.jpg')
    expect(isJitConversationKeyframePinned(mirror, 7)).toBe(true)
    expect(listPendingJitKeyframeCleanup(mirror, 100)).toHaveLength(0)
    expect(listPendingJitKeyframeCleanup(mirror, 2_200)).toHaveLength(1)
  })

  it('retries independently and retires the mapped agent conversation pin after unlink succeeds', async () => {
    const db = new DatabaseSync(':memory:')
    initializeJitTriggerMirror(db as unknown as JitMirrorDb)
    const mirror = db as unknown as JitMirrorDb
    pinJitConversationKeyframe(mirror, {
      frameId: 8,
      ownerId: 'owner',
      conversationId: 'agent-conversation-for-chat-session',
      imagePath: 'C:/rewind/8.jpg'
    })
    enqueueJitKeyframeCleanup(
      mirror,
      {
        frameId: 8,
        ownerId: 'owner',
        conversationId: 'agent-conversation-for-chat-session',
        imagePath: 'C:/rewind/8.jpg'
      },
      0
    )
    const removeFile = vi.fn(async () => undefined)
    const deleteFrame = vi.fn()
    const removed = await drainJitKeyframeCleanup({
      db: mirror,
      readFrame: () => null,
      removeFile,
      deleteFrame,
      now: () => 0
    })
    expect(removed).toBe(1)
    expect(removeFile).toHaveBeenCalledWith('C:/rewind/8.jpg')
    expect(deleteFrame).toHaveBeenCalledWith(8)
    expect(isJitConversationKeyframePinned(mirror, 8)).toBe(false)
    expect(listPendingJitKeyframeCleanup(mirror, 0)).toHaveLength(0)
  })

  it('keeps both retry authority and pin when reference retirement faults mid-transaction', async () => {
    const db = new DatabaseSync(':memory:')
    initializeJitTriggerMirror(db as unknown as JitMirrorDb)
    const mirror = db as unknown as JitMirrorDb
    pinJitConversationKeyframe(mirror, {
      frameId: 9,
      ownerId: 'owner',
      conversationId: 'kernel-conversation-9',
      imagePath: 'C:/rewind/9.jpg'
    })
    enqueueJitKeyframeCleanup(
      mirror,
      {
        frameId: 9,
        ownerId: 'owner',
        conversationId: 'kernel-conversation-9',
        imagePath: 'C:/rewind/9.jpg'
      },
      0
    )

    let fault = true
    const faultingDb: JitMirrorDb = {
      exec: (sql) => db.exec(sql),
      prepare: (sql) => {
        if (fault && sql.startsWith('DELETE FROM jit_keyframe_pin')) {
          fault = false
          throw new Error('injected pin-retirement fault')
        }
        return db.prepare(sql) as unknown as JitMirrorStatement
      }
    }

    const removeFile = vi.fn(async () => undefined)
    const removed = await drainJitKeyframeCleanup({
      db: faultingDb,
      readFrame: () => null,
      removeFile,
      deleteFrame: vi.fn(),
      now: () => 0
    })
    expect(removed).toBe(0)
    expect(isJitConversationKeyframePinned(mirror, 9)).toBe(true)
    expect(listPendingJitKeyframeCleanup(mirror, 2_200)).toHaveLength(1)
  })
})
