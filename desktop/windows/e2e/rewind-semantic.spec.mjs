/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Rewind semantic-search E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and proves the whole main-process pipeline end to end —
// session relay -> launch backfill -> Gemini proxy call -> vectors persisted ->
// hybrid search merge — with nothing mocked inside the app.
//
// The Gemini proxy is intercepted WITHOUT touching production code: the session
// relayed over `rewind:setEmbedSession` carries its own `desktopApiBase`, so we
// point the app at a local stub server and it makes real net.fetch calls to it.
// No real Gemini/Firebase credentials are involved, and no live API is hit.
//
// Frames are seeded by pre-creating the SQLite file that OMI_DB_PATH points at
// (the app's schema bootstrap creates the FTS index + triggers and backfills them
// from these rows), so the backfill has real work to find on launch.
//
// Build first, then run: `pnpm test:e2e:rewind-semantic`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { createServer } from 'node:http'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')

const EMBED_DIM = 3072
const MODEL = 'gemini-embedding-001'

// Frame A: no keyword overlap with the query — it can ONLY be found semantically.
const DOC_A = 'gradient descent optimizer learning rate schedule'
// Frame B: contains the query's words — this is the keyword (FTS) hit.
const DOC_B = 'Q3 quarterly revenue projections for the board deck'
// Frame C: unrelated to both, and semantically orthogonal — must not appear.
const DOC_C = 'chocolate chip cookie recipe with brown butter'
const QUERY = 'quarterly revenue projections'

/** A 3072-dim one-hot unit vector — already normalized, like the real API's output. */
function basisVector(index) {
  const values = new Array(EMBED_DIM).fill(0)
  values[index] = 1
  return values
}

// The stub's semantic "space": the query is deliberately aligned with FRAME A
// (cosine 1.0) and orthogonal to B and C (cosine 0). So a correct merge returns
// B first (keyword) and then adds A (semantic recall FTS could never find).
function vectorForText(text) {
  if (text === DOC_A) return basisVector(0)
  if (text === DOC_B) return basisVector(1)
  if (text === DOC_C) return basisVector(2)
  if (text === QUERY) return basisVector(0) // == DOC_A
  return basisVector(7) // anything else: orthogonal to all of the above
}

/** Stub of the desktop-backend Gemini proxy. Records every call it receives. */
async function startProxyStub() {
  const calls = []
  let failEmbedContent = false

  const server = createServer((req, res) => {
    let body = ''
    req.on('data', (c) => (body += c))
    req.on('end', () => {
      const payload = JSON.parse(body || '{}')
      calls.push({
        url: req.url,
        auth: req.headers.authorization,
        payload
      })

      // The non-fatal path: a dead embedding backend must degrade search to
      // keyword-only rather than erroring out.
      if (failEmbedContent && req.url.endsWith(':embedContent')) {
        res.writeHead(500).end('{}')
        return
      }

      res.writeHead(200, { 'Content-Type': 'application/json' })
      if (req.url.endsWith(':batchEmbedContents')) {
        const embeddings = payload.requests.map((r) => ({
          values: vectorForText(r.content.parts[0].text)
        }))
        res.end(JSON.stringify({ embeddings }))
      } else {
        res.end(
          JSON.stringify({
            embedding: { values: vectorForText(payload.content.parts[0].text) }
          })
        )
      }
    })
  })

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  return {
    base: `http://127.0.0.1:${server.address().port}`,
    calls,
    setFailEmbedContent: (v) => (failEmbedContent = v),
    close: () => new Promise((r) => server.close(r))
  }
}

/** Pre-create omi.db with three OCR'd frames for the backfill to find. */
function seedDb(dbPath) {
  const db = new DatabaseSync(dbPath)
  db.exec(`
    CREATE TABLE rewind_frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      app TEXT NOT NULL DEFAULT '',
      window_title TEXT NOT NULL DEFAULT '',
      process_name TEXT NOT NULL DEFAULT '',
      ocr_text TEXT NOT NULL DEFAULT '',
      image_path TEXT NOT NULL,
      width INTEGER NOT NULL DEFAULT 0,
      height INTEGER NOT NULL DEFAULT 0,
      indexed INTEGER NOT NULL DEFAULT 0
    );
  `)
  const now = Date.now()
  const insert = db.prepare(
    `INSERT INTO rewind_frames (id, ts, app, window_title, ocr_text, image_path, indexed)
     VALUES (?, ?, ?, ?, ?, ?, 1)`
  )
  // Distinct apps + timestamps so each lands in its own search group.
  insert.run(1, now - 30 * 60_000, 'Notes', 'ml notes', DOC_A, 'C:\\f\\1.jpg')
  insert.run(2, now - 20 * 60_000, 'Slides', 'board deck', DOC_B, 'C:\\f\\2.jpg')
  insert.run(3, now - 10 * 60_000, 'Browser', 'recipes', DOC_C, 'C:\\f\\3.jpg')
  db.close()
}

/** Read the vectors the app persisted (after it has exited). */
function storedEmbeddings(dbPath) {
  const db = new DatabaseSync(dbPath)
  const rows = db
    .prepare('SELECT frame_id, dim, model, vec FROM rewind_embeddings ORDER BY frame_id')
    .all()
  db.close()
  return rows
}

const until = async (label, fn, timeoutMs = 30_000) => {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const value = await fn()
    if (value) return value
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 250))
  }
}

test('embeds seeded frames via the proxy, then merges vector recall into FTS search', async (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-e2e-rewind-'))
  const dbPath = path.join(dir, 'omi.db')
  seedDb(dbPath)

  const stub = await startProxyStub()
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      OMI_DB_PATH: dbPath
    }
  })

  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    await stub.close()
    rmSync(dir, { recursive: true, force: true })
  })

  const win = await app.firstWindow()

  // Relay a session pointing at the stub. Re-pushed on a loop because the
  // renderer's own auth listener fires a sign-out clear (there is no signed-in
  // Firebase user in E2E) which would otherwise disarm the service; the last
  // write wins, and each arriving session re-kicks the backfill.
  const armSession = () =>
    win.evaluate(
      (base) => window.omi.rewindSetEmbedSession({ desktopApiBase: base, token: 'e2e-token' }),
      stub.base
    )

  const batchCall = await until('the backfill to call the proxy', async () => {
    await armSession()
    return stub.calls.find((c) => c.url.endsWith(':batchEmbedContents'))
  })

  // --- The indexer called the real proxy, correctly. ---
  assert.equal(batchCall.url, `/v1/proxy/gemini/models/${MODEL}:batchEmbedContents`)
  assert.equal(batchCall.auth, 'Bearer e2e-token', 'sends the relayed Firebase token')
  const sent = batchCall.payload.requests
  assert.equal(sent.length, 3, 'all three seeded frames in one batch')
  for (const r of sent) {
    assert.equal(r.model, `models/${MODEL}`)
    assert.equal(r.taskType, 'RETRIEVAL_DOCUMENT', 'stored passages, not a query')
  }
  assert.deepEqual(sent.map((r) => r.content.parts[0].text).sort(), [DOC_A, DOC_B, DOC_C].sort())

  // --- Hybrid search: FTS leads, the semantic hit is added. ---
  const groups = await until('search to return the semantic hit', async () => {
    const g = await win.evaluate((q) => window.omi.rewindSearch(q), QUERY)
    return g.length >= 2 ? g : null
  })

  const queryCall = stub.calls.find((c) => c.url.endsWith(':embedContent'))
  assert.equal(queryCall.payload.taskType, 'RETRIEVAL_QUERY', 'the query uses the query task type')
  assert.equal(queryCall.payload.content.parts[0].text, QUERY)

  const frameIds = groups.map((g) => g.representative.id)
  // Frame 2 is the keyword hit and MUST lead. Frame 1 shares no words with the
  // query at all — it is here purely because its vector matched, which is the
  // whole point of the feature.
  assert.equal(frameIds[0], 2, 'FTS result leads')
  assert.ok(frameIds.includes(1), 'vector recall added the frame FTS could not find')
  assert.ok(!frameIds.includes(3), 'the orthogonal frame stays out (below the 0.5 floor)')

  // --- Vector failure is non-fatal: keyword results must still render. ---
  stub.setFailEmbedContent(true)
  const degraded = await win.evaluate((q) => window.omi.rewindSearch(q), QUERY)
  assert.equal(degraded.length, 1, 'degrades to keyword-only instead of erroring')
  assert.equal(degraded[0].representative.id, 2)

  await app.close()

  // --- Vectors were really persisted: one normalized row per frame. ---
  const rows = storedEmbeddings(dbPath)
  assert.equal(rows.length, 3, 'a vector row per seeded frame')
  for (const row of rows) {
    assert.equal(row.dim, EMBED_DIM)
    assert.equal(row.model, MODEL)
    assert.equal(row.vec.byteLength, EMBED_DIM * 4, '12288-byte Float32 BLOB')
  }
})
