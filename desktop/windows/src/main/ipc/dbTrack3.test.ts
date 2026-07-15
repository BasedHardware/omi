// Track 3 (proactive intelligence & memory) schema + storage contract, proven
// against a REAL SQLite database via node:sqlite — better-sqlite3 in this repo
// is built for Electron's ABI and won't load under plain-node vitest (same
// reason dbMigrations.test.ts / dbWipe.test.ts use node:sqlite). The DDL and SQL
// below are a hand-maintained copy of db.ts's Track 3 block and readers/writers,
// tested here for semantics (not diffed against db.ts); the pure Float32⇄BLOB
// conversion is exercised as the real db.ts code via the imported
// taskEmbeddingVector helpers.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { bufferToVector, vectorToBuffer } from './taskEmbeddingVector'

// Verbatim from db.ts's `/* ---- Track 3 ---- */` CREATE block.
const TRACK3_SCHEMA = `
  CREATE TABLE IF NOT EXISTS ai_user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_text TEXT NOT NULL,
    data_sources_used TEXT,
    generated_at INTEGER NOT NULL,
    backend_synced INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_ai_user_profiles_generated_at ON ai_user_profiles(generated_at);

  CREATE TABLE IF NOT EXISTS focus_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screenshot_id TEXT,
    status TEXT NOT NULL,
    app_or_site TEXT,
    description TEXT,
    message TEXT,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    backend_id TEXT,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    window_title TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_focus_sessions_created_at ON focus_sessions(created_at);

  CREATE TABLE IF NOT EXISTS task_embeddings (
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    vector BLOB NOT NULL,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (source, item_id)
  );

  CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    source_app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    context_summary TEXT NOT NULL DEFAULT '',
    confidence REAL,
    screenshot_id INTEGER,
    backend_id TEXT,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
`

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec(TRACK3_SCHEMA)
  return db
}

function tableNames(db: DatabaseSync): string[] {
  return (
    db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all() as {
      name: string
    }[]
  ).map((r) => r.name)
}

describe('Track 3 schema', () => {
  it('creates the three net-new tables', () => {
    const names = tableNames(makeDb())
    for (const t of ['ai_user_profiles', 'focus_sessions', 'task_embeddings', 'memories']) {
      expect(names, `table ${t}`).toContain(t)
    }
  })

  it('task_embeddings uses a composite (source, item_id) primary key', () => {
    const db = makeDb()
    const pk = (
      db.prepare('PRAGMA table_info(task_embeddings)').all() as { name: string; pk: number }[]
    )
      .filter((c) => c.pk > 0)
      .sort((a, b) => a.pk - b.pk)
      .map((c) => c.name)
    expect(pk).toEqual(['source', 'item_id'])
  })
})

describe('ai_user_profiles round-trip', () => {
  it('inserts, lists newest-first, updates text, marks synced, and deletes', () => {
    const db = makeDb()
    const insert = db.prepare(
      'INSERT INTO ai_user_profiles (profile_text, data_sources_used, generated_at, backend_synced) VALUES (?, ?, ?, ?)'
    )
    insert.run('older profile', JSON.stringify(['conversations']), 1000, 0)
    const newer = insert.run('newer profile', JSON.stringify(['conversations', 'files']), 2000, 0)

    // Newest first (default consolidation read).
    const list = db
      .prepare(
        'SELECT id, profile_text AS profileText, data_sources_used AS dataSourcesUsed, generated_at AS generatedAt, backend_synced AS backendSynced FROM ai_user_profiles ORDER BY generated_at DESC, id DESC LIMIT 5'
      )
      .all() as {
      profileText: string
      dataSourcesUsed: string
      generatedAt: number
      backendSynced: number
    }[]
    expect(list.map((r) => r.profileText)).toEqual(['newer profile', 'older profile'])
    expect(JSON.parse(list[0].dataSourcesUsed)).toEqual(['conversations', 'files'])

    const newerId = Number(newer.lastInsertRowid)
    db.prepare('UPDATE ai_user_profiles SET profile_text = ? WHERE id = ?').run('edited', newerId)
    db.prepare('UPDATE ai_user_profiles SET backend_synced = 1 WHERE id = ?').run(newerId)
    const edited = db
      .prepare(
        'SELECT profile_text AS profileText, backend_synced AS backendSynced FROM ai_user_profiles WHERE id = ?'
      )
      .get(newerId) as { profileText: string; backendSynced: number }
    expect(edited.profileText).toBe('edited')
    expect(edited.backendSynced).toBe(1)

    db.prepare('DELETE FROM ai_user_profiles WHERE id = ?').run(newerId)
    expect(
      (db.prepare('SELECT COUNT(*) AS n FROM ai_user_profiles').get() as { n: number }).n
    ).toBe(1)
    db.prepare('DELETE FROM ai_user_profiles').run()
    expect(
      (db.prepare('SELECT COUNT(*) AS n FROM ai_user_profiles').get() as { n: number }).n
    ).toBe(0)
  })

  it('maps NULL data_sources_used to an empty array (mapper null/empty path)', () => {
    const db = makeDb()
    // db.ts can't be imported here (it pulls in better-sqlite3/electron — see the
    // file header), so replicate the exact `parseJsonArray(x) ?? []` the mapper uses.
    const parseJsonArray = (s: string | null): string[] | undefined => {
      if (!s) return undefined
      try {
        const v = JSON.parse(s)
        return Array.isArray(v) ? (v as string[]) : undefined
      } catch {
        return undefined
      }
    }
    db.prepare(
      'INSERT INTO ai_user_profiles (profile_text, data_sources_used, generated_at, backend_synced) VALUES (?, ?, ?, ?)'
    ).run('no sources', null, 1000, 0)
    const row = db
      .prepare('SELECT data_sources_used AS dataSourcesUsed FROM ai_user_profiles')
      .get() as { dataSourcesUsed: string | null }
    expect(row.dataSourcesUsed).toBeNull()
    expect(parseJsonArray(row.dataSourcesUsed) ?? []).toEqual([])
  })
})

describe('focus_sessions round-trip', () => {
  it('inserts, filters by since, orders newest-first, and marks synced', () => {
    const db = makeDb()
    const insert = db.prepare(
      `INSERT INTO focus_sessions
         (screenshot_id, status, app_or_site, description, message, duration_seconds, backend_id, backend_synced, created_at, window_title)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    insert.run('shot-1', 'focused', 'VS Code', 'coding', 'nice work', 120, null, 0, 1000, 'main.ts')
    const distracted = insert.run(
      'shot-2',
      'distracted',
      'YouTube',
      'watching',
      'refocus?',
      60,
      null,
      0,
      2000,
      'video'
    )

    // since filter + newest-first.
    const since = db
      .prepare(
        'SELECT status, created_at AS createdAt FROM focus_sessions WHERE created_at >= ? ORDER BY created_at DESC, id DESC'
      )
      .all(1500) as { status: string; createdAt: number }[]
    expect(since).toHaveLength(1)
    expect(since[0].status).toBe('distracted')

    const all = db
      .prepare('SELECT status FROM focus_sessions ORDER BY created_at DESC, id DESC')
      .all() as { status: string }[]
    expect(all.map((r) => r.status)).toEqual(['distracted', 'focused'])

    const id = Number(distracted.lastInsertRowid)
    db.prepare('UPDATE focus_sessions SET backend_synced = 1, backend_id = ? WHERE id = ?').run(
      'be-99',
      id
    )
    const synced = db
      .prepare(
        'SELECT backend_id AS backendId, backend_synced AS backendSynced FROM focus_sessions WHERE id = ?'
      )
      .get(id) as { backendId: string; backendSynced: number }
    expect(synced.backendId).toBe('be-99')
    expect(synced.backendSynced).toBe(1)
  })
})

describe('memories round-trip', () => {
  // Mirrors db.ts insertMemory / markMemorySynced / recentMemories, exercised
  // through the same DDL the app ships (TRACK3_SCHEMA is a verbatim copy).
  const INSERT = `INSERT INTO memories
       (content, category, source_app, window_title, context_summary, confidence, screenshot_id, backend_id, backend_synced, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  const RECENT = 'SELECT content, category FROM memories ORDER BY created_at DESC, id DESC LIMIT ?'

  it('inserts a row, defaulting the optional text columns to empty strings', () => {
    const db = makeDb()
    // insertMemory passes '' for the three text columns when the caller omits them.
    db.prepare(INSERT).run('User works at Acme', 'system', '', '', '', 0.9, null, null, 0, 1000)
    const row = db
      .prepare(
        'SELECT content, category, source_app AS sourceApp, window_title AS windowTitle, context_summary AS contextSummary, confidence, backend_synced AS backendSynced FROM memories'
      )
      .get() as {
      content: string
      category: string
      sourceApp: string
      windowTitle: string
      contextSummary: string
      confidence: number
      backendSynced: number
    }
    expect(row).toMatchObject({
      content: 'User works at Acme',
      category: 'system',
      sourceApp: '',
      windowTitle: '',
      contextSummary: '',
      confidence: 0.9,
      backendSynced: 0
    })
  })

  it('recentMemories returns content+category newest-first, capped at the limit', () => {
    const db = makeDb()
    db.prepare(INSERT).run('oldest', 'system', 'Slack', 't', 'c', 0.8, 1, null, 0, 1000)
    db.prepare(INSERT).run('middle', 'interesting', 'X', 't', 'c', 0.9, 2, null, 0, 2000)
    db.prepare(INSERT).run('newest', 'system', 'Notion', 't', 'c', 0.95, 3, null, 0, 3000)

    const recent = db.prepare(RECENT).all(2) as { content: string; category: string }[]
    expect(recent).toEqual([
      { content: 'newest', category: 'system' },
      { content: 'middle', category: 'interesting' }
    ])
  })

  it('markMemorySynced stamps backend_id + backend_synced', () => {
    const db = makeDb()
    const r = db.prepare(INSERT).run('m', 'system', 'App', 't', 'c', 0.8, null, null, 0, 1000)
    const id = Number(r.lastInsertRowid)
    db.prepare('UPDATE memories SET backend_synced = 1, backend_id = ? WHERE id = ?').run(
      'mem-42',
      id
    )
    const synced = db
      .prepare(
        'SELECT backend_id AS backendId, backend_synced AS backendSynced FROM memories WHERE id = ?'
      )
      .get(id) as { backendId: string; backendSynced: number }
    expect(synced).toEqual({ backendId: 'mem-42', backendSynced: 1 })
  })

  it('stores a NULL confidence when the caller passes null', () => {
    const db = makeDb()
    db.prepare(INSERT).run('no conf', 'system', 'App', 't', 'c', null, null, null, 0, 1000)
    const row = db.prepare('SELECT confidence FROM memories').get() as { confidence: number | null }
    expect(row.confidence).toBeNull()
  })
})

describe('task_embeddings round-trip', () => {
  const UPSERT = `INSERT INTO task_embeddings (source, item_id, vector, text, model, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(source, item_id) DO UPDATE SET
       vector = excluded.vector, text = excluded.text, model = excluded.model, updated_at = excluded.updated_at`
  const SELECT_ONE =
    'SELECT source, item_id AS itemId, vector, text, model, updated_at AS updatedAt FROM task_embeddings WHERE source = ? AND item_id = ?'

  it('round-trips a Float32 vector through the BLOB column (real db.ts helpers)', () => {
    const db = makeDb()
    const vec = new Float32Array([0.5, -0.25, 1.0, 0.0, 3.14159])
    db.prepare(UPSERT).run(
      'action_item',
      'a1',
      vectorToBuffer(vec),
      'buy milk',
      'gemini-embedding-001',
      1000
    )

    const row = db.prepare(SELECT_ONE).get('action_item', 'a1') as {
      vector: Uint8Array
      text: string
    }
    const back = bufferToVector(row.vector)
    expect(Array.from(back)).toEqual(Array.from(vec))
    expect(row.text).toBe('buy milk')
  })

  it('bufferToVector(vectorToBuffer(v)) is identity (pure helper)', () => {
    const v = new Float32Array([1.5, 2.5, -7.0, 0.001])
    expect(Array.from(bufferToVector(vectorToBuffer(v)))).toEqual(Array.from(v))
  })

  it('upsert on the same (source, item_id) updates in place, never duplicates', () => {
    const db = makeDb()
    const v1 = new Float32Array([1, 0, 0])
    const v2 = new Float32Array([0, 1, 0])
    db.prepare(UPSERT).run('action_item', 'a1', vectorToBuffer(v1), 'first', 'm1', 1000)
    db.prepare(UPSERT).run('action_item', 'a1', vectorToBuffer(v2), 'second', 'm2', 2000)

    expect((db.prepare('SELECT COUNT(*) AS n FROM task_embeddings').get() as { n: number }).n).toBe(
      1
    )
    const row = db.prepare(SELECT_ONE).get('action_item', 'a1') as {
      vector: Uint8Array
      text: string
      model: string
      updatedAt: number
    }
    expect(row.text).toBe('second')
    expect(row.model).toBe('m2')
    expect(row.updatedAt).toBe(2000)
    expect(Array.from(bufferToVector(row.vector))).toEqual([0, 1, 0])
  })

  it('same item_id under a different source does NOT collide (composite-PK fix)', () => {
    const db = makeDb()
    db.prepare(UPSERT).run(
      'action_item',
      'shared-id',
      vectorToBuffer(new Float32Array([1, 1])),
      'ai',
      'm',
      1
    )
    db.prepare(UPSERT).run(
      'staged_task',
      'shared-id',
      vectorToBuffer(new Float32Array([2, 2])),
      'st',
      'm',
      1
    )

    expect((db.prepare('SELECT COUNT(*) AS n FROM task_embeddings').get() as { n: number }).n).toBe(
      2
    )
    const ai = db.prepare(SELECT_ONE).get('action_item', 'shared-id') as { vector: Uint8Array }
    const st = db.prepare(SELECT_ONE).get('staged_task', 'shared-id') as { vector: Uint8Array }
    expect(Array.from(bufferToVector(ai.vector))).toEqual([1, 1])
    expect(Array.from(bufferToVector(st.vector))).toEqual([2, 2])
  })

  it('deletes a single embedding by (source, item_id)', () => {
    const db = makeDb()
    db.prepare(UPSERT).run('action_item', 'a1', vectorToBuffer(new Float32Array([1])), 't', 'm', 1)
    db.prepare(UPSERT).run('staged_task', 's1', vectorToBuffer(new Float32Array([2])), 't', 'm', 1)
    db.prepare('DELETE FROM task_embeddings WHERE source = ? AND item_id = ?').run(
      'action_item',
      'a1'
    )
    const rows = db.prepare('SELECT source FROM task_embeddings').all() as { source: string }[]
    expect(rows.map((r) => r.source)).toEqual(['staged_task'])
  })

  it('round-trips an empty vector and reads a zero-length blob back as an empty vector', () => {
    // Pure conversion holds for the empty case.
    expect(bufferToVector(vectorToBuffer(new Float32Array(0)))).toEqual(new Float32Array(0))

    // A stored zero-length BLOB reads back through bufferToVector as an empty
    // vector. Inserted via the X'' literal because node:sqlite binds a 0-length
    // Buffer as NULL (unlike better-sqlite3 in prod), which the NOT NULL column
    // rejects — a test-harness quirk, not a code path we ship.
    const db = makeDb()
    db.prepare(
      "INSERT INTO task_embeddings (source, item_id, vector, text, model, updated_at) VALUES ('action_item', 'empty', X'', 'no vec', 'm', 1)"
    ).run()
    const row = db.prepare(SELECT_ONE).get('action_item', 'empty') as { vector: Uint8Array }
    expect(row.vector.byteLength).toBe(0)
    expect(bufferToVector(row.vector)).toEqual(new Float32Array(0))
  })

  it('round-trips a 3072-dim vector byte-exact (real Gemini embedding size)', () => {
    const vec = new Float32Array(3072)
    for (let i = 0; i < vec.length; i++) vec[i] = Math.sin(i) // arbitrary, distinct float32s
    const db = makeDb()
    db.prepare(UPSERT).run(
      'action_item',
      'big',
      vectorToBuffer(vec),
      'big',
      'gemini-embedding-001',
      1
    )
    const row = db.prepare(SELECT_ONE).get('action_item', 'big') as { vector: Uint8Array }
    const back = bufferToVector(row.vector)
    expect(back.length).toBe(3072)
    expect(Array.from(back)).toEqual(Array.from(vec))
  })
})
