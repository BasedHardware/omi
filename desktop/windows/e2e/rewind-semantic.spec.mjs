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
import { createHash } from 'node:crypto'
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
// Frame E: OLD (older than the retention window we set). Its vector is derived
// from the user's screen, so retention must delete it along with the frame.
const DOC_E = 'expired private banking password reset page'
const QUERY = 'quarterly revenue projections'

/** A 3072-dim one-hot unit vector — already normalized, like the real API's output. */
function basisVector(index) {
  const values = new Array(EMBED_DIM).fill(0)
  values[index] = 1
  return values
}

// What the app actually sends for a stored frame: the OCR text with its app context
// prepended — macOS's `"[<app>] <windowTitle>\n<ocrText>"` (rewind/embedVector.ts
// formatForEmbedding, ported from OCREmbeddingService.swift:43-50). A search QUERY
// is sent raw (macOS embeds the bare query too — OCREmbeddingService.swift:259);
// the asymmetry is what RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY is for.
const embedded = (app, title, ocrText) => `[${app}] ${title}\n${ocrText}`

// Each seeded frame's composed document text. If the app stopped embedding the app
// context (or composed it differently), these keys would stop matching and every
// frame would fall through to the orthogonal basisVector(7) — no semantic hit, and
// the merge assertions below would fail. So this pins the composition end to end.
const DOC_A_EMBEDDED = embedded('Notes', 'ml notes', DOC_A)
const DOC_B_EMBEDDED = embedded('Slides', 'board deck', DOC_B)
const DOC_C_EMBEDDED = embedded('Browser', 'recipes', DOC_C)
const DOC_E_EMBEDDED = embedded('Bank', 'reset', DOC_E)

// The stub's semantic "space": the query is deliberately aligned with FRAME A
// (cosine 1.0) and orthogonal to B and C (cosine 0). So a correct merge returns
// B first (keyword) and then adds A (semantic recall FTS could never find).
function vectorForText(text) {
  if (text === DOC_A_EMBEDDED) return basisVector(0)
  if (text === DOC_B_EMBEDDED) return basisVector(1)
  if (text === DOC_C_EMBEDDED) return basisVector(2)
  if (text === DOC_E_EMBEDDED) return basisVector(3)
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

/** Pre-create omi.db with three OCR'd frames for the backfill to find.
 *
 *  The database is seeded in the shape a SHIPPED `main` build leaves behind —
 *  including its vector-per-frame `rewind_embeddings` (frame_id, dim, model, vec,
 *  created_at), which has no `hash` column. That is what every upgrading user
 *  actually has on disk, and indexing `hash` on it used to throw out of the schema
 *  bootstrap and take the whole app down (not just Rewind: `get()` is the one
 *  un-try/caught singleton behind every DB-backed IPC handler). If that regresses,
 *  this app never reaches its first window and the test dies here. */
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
    -- PR0-era table, verbatim from origin/main. Never written to; upgrading a
    -- database that has it must be lossless AND must not throw.
    CREATE TABLE rewind_embeddings (
      frame_id INTEGER PRIMARY KEY,
      dim INTEGER,
      model TEXT,
      vec BLOB,
      created_at INTEGER
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
  // Frame 4 is a re-screenshot of frame 2's window: byte-identical OCR text. It
  // must cost ONE API item and ONE stored vector between them, while both frames
  // stay independently findable.
  insert.run(4, now - 5 * 60_000, 'Slides', 'board deck', DOC_B, 'C:\\f\\4.jpg')
  // Frame 5 is THREE DAYS old — past the 1-day retention we set below.
  insert.run(5, now - 3 * 24 * 60 * 60_000, 'Bank', 'reset', DOC_E, 'C:\\f\\5.jpg')
  db.close()
}

/** Read what the app persisted (after it has exited): one mapping row per frame,
 *  joined to the single vector stored for that frame's content. */
function storedEmbeddings(dbPath) {
  const db = new DatabaseSync(dbPath)
  const rows = db
    .prepare(
      `SELECT e.frame_id AS frame_id, e.hash AS hash, v.dim AS dim, v.model AS model, v.vec AS vec
         FROM rewind_embeddings e
         JOIN rewind_embedding_vectors v ON v.hash = e.hash
        ORDER BY e.frame_id`
    )
    .all()
  const vectorCount = db.prepare('SELECT COUNT(*) AS n FROM rewind_embedding_vectors').get().n
  db.close()
  return { rows, vectorCount }
}

/** Every vector hash still in the store (after the app has exited). */
function orphanHashes(dbPath) {
  const db = new DatabaseSync(dbPath)
  const rows = db.prepare('SELECT hash FROM rewind_embedding_vectors').all()
  db.close()
  return rows.map((r) => r.hash)
}

/** The app's content key: first 16 bytes of SHA-256, hex (see embedVector.ts). */
function sha256_16(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 32)
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
  for (const r of sent) {
    assert.equal(r.model, `models/${MODEL}`)
    assert.equal(r.taskType, 'RETRIEVAL_DOCUMENT', 'stored passages, not a query')
  }
  // FIVE frames were seeded but only FOUR distinct texts exist — frames 2 and 4
  // carry byte-identical OCR. The duplicate is deduped away BEFORE the request,
  // which is the ~20x API saving in miniature.
  assert.deepEqual(
    sent.map((r) => r.content.parts[0].text).sort(),
    [DOC_A_EMBEDDED, DOC_B_EMBEDDED, DOC_C_EMBEDDED, DOC_E_EMBEDDED].sort(),
    'each unique screen is sent once, WITH its app/window context (macOS parity)'
  )

  // --- Hybrid search, in two phases. ---
  // Frames 2 and 4 both contain the query's words, so they are the KEYWORD hits.
  // Frame 1 shares no words with the query at all.
  const ftsIds = [2, 4]

  // Collect phase-2 (semantic) pushes as they arrive.
  await win.evaluate(() => {
    window.__semantic = []
    window.omi.onRewindSearchResults((r) => window.__semantic.push(r))
  })

  // PHASE 1 — keyword results come back WITHOUT waiting on the embedding call.
  // This is the invariant that matters on a flaky network: the query embed can
  // burn ~91s of retries, and the FTS rows must not be held hostage behind it.
  const phase1 = await win.evaluate((q) => window.omi.rewindSearch(q), QUERY)
  assert.deepEqual(
    phase1.map((g) => g.representative.id).sort(),
    ftsIds,
    'phase 1 is keyword-only, and immediate'
  )

  // PHASE 2 — the semantic hit arrives out-of-band and is merged in.
  const groups = await until('the semantic hit to be pushed', async () => {
    await win.evaluate((q) => window.omi.rewindSearch(q), QUERY)
    return win.evaluate((q) => {
      const last = [...window.__semantic].reverse().find((r) => r.query === q)
      return last && last.groups.some((x) => x.representative.id === 1) ? last.groups : null
    }, QUERY)
  })

  const queryCall = stub.calls.find((c) => c.url.endsWith(':embedContent'))
  assert.equal(queryCall.payload.taskType, 'RETRIEVAL_QUERY', 'the query uses the query task type')
  assert.equal(queryCall.payload.content.parts[0].text, QUERY)

  const frameIds = groups.map((g) => g.representative.id)
  // Every keyword hit leads; the semantic-only frame is appended AFTER them and
  // never displaces one — that is the whole merge contract, and it must survive
  // GROUPING, which used to re-sort it all by timestamp.
  assert.deepEqual(frameIds.slice(0, 2).sort(), ftsIds, 'FTS results lead')
  assert.equal(frameIds[frameIds.length - 1], 1, 'vector recall is appended, not promoted')
  // Frame 1 is here PURELY because its vector matched — the point of the feature.
  assert.ok(!frameIds.includes(3), 'the orthogonal frame stays out (below the 0.5 floor)')

  // --- Vector failure is non-fatal: keyword results must still render. ---
  stub.setFailEmbedContent(true)
  await win.evaluate(() => (window.__semantic = []))
  const degraded = await win.evaluate((q) => window.omi.rewindSearch(q), QUERY)
  assert.deepEqual(
    degraded.map((g) => g.representative.id).sort(),
    ftsIds,
    'degrades to keyword-only instead of erroring'
  )
  // ...and no phase-2 push ever contradicts that (a dead embed leg stays silent).
  assert.deepEqual(
    await win.evaluate(() => window.__semantic),
    [],
    'a failed query embed pushes nothing'
  )

  // --- PRIVACY: retention must delete the vectors, not just the frames. ---
  // Drives the REAL retention path (rewind:setSettings -> rewind:pruneNow ->
  // deleteRewindFramesOlderThan) through the app, so this covers db.ts itself and
  // not a replica of its SQL. A vector is derived from the user's screen: if it
  // outlives its frame, "delete my history" silently did not.
  const pruned = await win.evaluate(async () => {
    const s = await window.omi.rewindGetSettings()
    await window.omi.rewindSetSettings({ ...s, retentionDays: 1 })
    return window.omi.rewindPruneNow()
  })
  assert.equal(pruned, 1, 'the 3-day-old frame was pruned')

  await app.close()

  // --- Vectors were really persisted, deduped, and pruned. ---
  const { rows, vectorCount } = storedEmbeddings(dbPath)
  assert.equal(rows.length, 4, 'every surviving frame is mapped to its content')
  for (const row of rows) {
    assert.equal(row.dim, EMBED_DIM)
    assert.equal(row.model, MODEL)
    assert.equal(row.vec.byteLength, EMBED_DIM * 4, '12288-byte Float32 BLOB')
  }
  // Frames 2 and 4 carry byte-identical OCR text, so they share ONE stored vector:
  // 4 surviving frames, 3 unique contents. A 12KB vector per frame would instead
  // amplify the store by the duplicate ratio.
  assert.equal(vectorCount, 3, 'duplicate content stored exactly one vector')
  const dupHashes = rows.filter((r) => r.frame_id === 2 || r.frame_id === 4).map((r) => r.hash)
  assert.equal(dupHashes[0], dupHashes[1], 'the duplicate frames point at the same vector')

  // The pruned frame's mapping AND its vector are gone — no orphan left behind.
  assert.ok(!rows.some((r) => r.frame_id === 5), 'the pruned frame has no embedding row')
  assert.ok(
    !orphanHashes(dbPath).includes(sha256_16(DOC_E_EMBEDDED)),
    'the pruned screen content left NO vector behind'
  )
})
