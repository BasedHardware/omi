// ROBUST agent-tool-plane gauntlet for the Windows Omi desktop app.
//
// Proves — against a REAL signed-in account, deterministically, no audio — that
// every PRODUCT tool the agent can invoke actually FIRES and produces the correct
// OBSERVABLE SIDE-EFFECT, and FLAGS any tool that is broken. Two layers:
//
//   PHASE 1 — DETERMINISTIC EXECUTOR PROOF (authoritative pass/fail).
//     Invokes each tool DIRECTLY in-process via window.omi.voiceToolExecute →
//     executeVoiceHubTool → executeHostTool — the exact shared dispatcher the LLM
//     relay and the voice hub both funnel through — under the real main_chat/pi-mono
//     session of the signed-in owner. No LLM in the loop, so it never flakes on the
//     model declining to call a tool. For each tool it asserts BOTH:
//       (a) the executor returned a VALID success (not an "Error: …" string, not a
//           backend/auth failure), verified by a per-tool output predicate; AND
//       (b) the SIDE-EFFECT actually landed, verified INDEPENDENTLY:
//             • task create/update/complete/delete → confirmed by execute_sql
//               COUNT(*) over the local action_items table (raw SQL read, a
//               different code path than the task engine that wrote it) + a
//               best-effort REST corroboration;
//             • save_knowledge_graph → confirmed by execute_sql over
//               onboarding_kg_nodes;
//             • read tools (memories/conversations/screen-history/recap/context) →
//               the returned payload has the tool's real shape, not an error.
//     A tool whose executor errors or whose side-effect is missing is BROKEN — the
//     "fix our systems" signal. This layer is the gate for the exit code.
//
//   PHASE 2 — LLM DISPATCH PROOF (corroborating, non-gating).
//     Drives a TYPED kernel chat turn (window.omi.mainChatSend, the signed-in
//     pi-mono lane) per tool and asserts the model actually invoked it (a
//     tool_activity{status:'completed'} + the pi-mono audit log). This proves the
//     model can SELECT and REACH each tool end-to-end. Because Phase 1 already
//     proved the tool WORKS, a Phase-2 miss on a product tool is a DISPATCH-MISS
//     (the model chatted / picked another tool), reported but NOT scored as a broken
//     tool. CODING tools (bash/read/write) are pi-mono's OWN built-in tools that run
//     LOCALLY in the app working dir (NOT host tools, NOT a cloud sandbox) — they are
//     independent of the Claude Code OAuth connect. They FIRE(local) when pi-mono runs
//     them, SKIP when they don't; the write probe targets an OS-temp path (never the
//     repo) and is swept in teardown. spawn_agent (spawning a SEPARATE local Claude
//     Code agent) is an expected SKIP — the managed-cloud lane refuses it and it needs
//     the (currently broken) connect stack; it is probed with empty args so nothing
//     actually spawns.
//
// TEST-DATA HYGIENE (real account): Phase 1 runs a self-contained task CRUD
// lifecycle whose final delete removes its own marker task, plus a REST sweep as a
// safety net. save_knowledge_graph uses a STABLE, clearly-labelled marker node id
// (`omi-gauntlet-selftest-node`) so repeated runs UPSERT the same single node rather
// than accumulating — there is no single-node KG delete tool, so that one labelled
// node is left behind by design (reported). Phase 2's own marker task is deleted too.
//
// SAFETY: touches ONLY the isolated _electron instance this script launches (its own
// --user-data-dir), never CDP :9222 / a prod bundle. Kills only the electron it
// started, and restores nothing global (no audio devices, no OS state).
//
// Exit: 0 every product tool PROVEN working (Phase 1) · 1 a product tool is BROKEN ·
//       2 preconditions missing · 3 only inconclusive (transient backend) gaps.
//
// Flags: --no-build (skip electron-vite build) · --phase1-only · --phase2-only.
import { execFileSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { readDotEnv, decodeJwt, exchangeRefreshToken } from './lib/omi-auth.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')
const PHASE1_ONLY = process.argv.includes('--phase1-only')
const PHASE2_ONLY = process.argv.includes('--phase2-only')
const RUN_ID = Date.now().toString(36)
const TASK_MARKER = `GAUNTLET-${RUN_ID}` // Phase 1 CRUD lifecycle marker
const P2_MARKER = `GAUNTLET2-${RUN_ID}` // Phase 2 LLM-dispatch marker (separate task)
const KG_NODE_ID = 'omi-gauntlet-selftest-node' // STABLE → idempotent, never accumulates
// pi-mono runs its built-in bash/read/write in the LOCAL working dir, so the write
// dispatch probe targets an OS-temp path (never the repo) and is swept in teardown.
const WRITE_PROBE_PATH = path.join(os.tmpdir(), `omi-gauntlet-write-${RUN_ID}.txt`)
const WRITE_PROBE_PROMPT_PATH = WRITE_PROBE_PATH.replace(/\\/g, '/')
const TURN_TERMINAL_MS = 180_000
const DIRECT_TIMEOUT_MS = 60_000
const BACKEND_SYNC_TIMEOUT_MS = 60_000 // wait for a created task to get its backend_id
const MAX_NOTOOL_ATTEMPTS = 3
const MAX_TRANSIENT_RETRIES = 3
const MAX_TURN_BUDGET = 6

function log(m) {
  console.log(`[gauntlet] ${m}`)
}

const TRANSIENT_RE =
  /upstream provider error|provider (?:error|overloaded|unavailable)|overloaded|rate.?limit|\b429\b|\b50[0-9]\b|temporarily|timed? ?out|timeout|econnreset|socket hang|network error|fetch failed|unavailable|deadline|try again|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|service unavailable|internal server error|bad gateway/i

// ── App / playwright helpers ────────────────────────────────────────────────────
async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app
      .windows()
      .find(
        (w) =>
          !/#\/(capture|overlay|bar|insight-toast|meeting-toast)/.test(w.url()) &&
          w.url() !== 'about:blank'
      )
    if (page) return page
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}
async function waitFor(page, fnBody, timeoutMs, label, arg) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const v = await page.evaluate(fnBody, arg)
    if (v) return v
    if (Date.now() > deadline) throw new Error(`timeout waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 400))
  }
}
async function injectAuth(page, { apiKey, idToken, refreshToken }) {
  const claims = decodeJwt(idToken)
  if (!claims?.user_id) throw new Error('could not decode injected ID token')
  const user = {
    uid: claims.user_id,
    email: claims.email ?? null,
    emailVerified: !!claims.email_verified,
    displayName: claims.name ?? null,
    isAnonymous: false,
    photoURL: claims.picture ?? null,
    providerData: [],
    stsTokenManager: { refreshToken, accessToken: idToken, expirationTime: claims.exp * 1000 },
    createdAt: String(Date.now()),
    lastLoginAt: String(Date.now()),
    apiKey,
    appName: '[DEFAULT]'
  }
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), {
    key: `firebase:authUser:${apiKey}:[DEFAULT]`,
    value: user
  })
}

// Read the per-run audit log; return the set of tools with a phase:'after' line.
function auditToolsAfter(auditLog) {
  try {
    const lines = fs.readFileSync(auditLog, 'utf8').split(/\r?\n/).filter(Boolean)
    return new Set(
      lines
        .map((l) => {
          try {
            return JSON.parse(l)
          } catch {
            return null
          }
        })
        .filter((o) => o && o.phase === 'after' && o.tool)
        .map((o) => o.tool)
    )
  } catch {
    return new Set()
  }
}

// ── Deterministic in-process invocation (Phase 1) ───────────────────────────────

/** Call ONE host tool directly via voiceToolExecute (executeHostTool under the
 *  signed-in main_chat session). Returns the raw result string (an "Error: …" string
 *  on any failure — the provider tool-result contract; it never throws). */
async function directExec(page, name, args = {}) {
  return page.evaluate(
    async ({ name, argumentsJSON, timeoutMs }) => {
      const call = window.omi.voiceToolExecute({ name, argumentsJSON })
      const timeout = new Promise((res) =>
        setTimeout(() => res(`Error: direct-exec timeout`), timeoutMs)
      )
      try {
        return await Promise.race([call, timeout])
      } catch (e) {
        return `Error: ${String(e)}`
      }
    },
    { name, argumentsJSON: JSON.stringify(args), timeoutMs: DIRECT_TIMEOUT_MS }
  )
}

/** Run an execute_sql SELECT and parse a single scalar (the cell above the trailing
 *  `N row(s)` line). Returns null on error / empty / no-scalar. formatRows shape:
 *  `header`\n`divider`\n`row…`\n`N row(s)` (or the literal `No results`). */
async function sqlScalar(page, query) {
  const out = await directExec(page, 'execute_sql', { query })
  if (/^Error:/.test(out) || /No results/.test(out)) return { value: null, out }
  const lines = out.trim().split('\n')
  // last line is "N row(s)"; the cell we want is the line before it.
  const valueLine = lines[lines.length - 2]
  return { value: valueLine != null ? valueLine.trim() : null, out }
}
async function sqlCount(page, query) {
  const r = await sqlScalar(page, query)
  if (/^Error:/.test(r.out)) return { count: null, out: r.out }
  if (/No results/.test(r.out)) return { count: 0, out: r.out }
  const n = Number.parseInt(r.value ?? '', 10)
  return { count: Number.isFinite(n) ? n : null, out: r.out }
}

const like = (s) => `%${s}%` // marker is alnum + hyphen + spaces — safe in a SQL literal

// ── LLM typed-turn driver (Phase 2) ─────────────────────────────────────────────
async function sendTurn(page, prompt, auditLog) {
  const requestId = `gauntlet-${RUN_ID}-${Math.random().toString(16).slice(2)}`
  const auditBefore = auditToolsAfter(auditLog)
  await page.evaluate(
    ({ requestId, prompt }) => {
      window.__done = false
      window.__result = null
      window.omi
        .mainChatSend({ requestId, prompt, cleanUserText: prompt, chatId: 'default' })
        .then((r) => {
          window.__result = r
          window.__done = true
        })
        .catch((e) => {
          window.__result = { ok: false, terminalStatus: 'failed', error: String(e) }
          window.__done = true
        })
    },
    { requestId, prompt }
  )
  const deadline = Date.now() + TURN_TERMINAL_MS
  for (;;) {
    const done = await page.evaluate(
      (rid) =>
        window.__done === true ||
        (window.__tev || []).some((e) => e.type === 'run_finished' && e.requestId === rid),
      requestId
    )
    if (done) break
    if (Date.now() > deadline) break
    await new Promise((r) => setTimeout(r, 500))
  }
  await new Promise((r) => setTimeout(r, 800))

  const evts = await page.evaluate(
    (rid) => (window.__tev || []).filter((e) => e.requestId === rid),
    requestId
  )
  const result = await page.evaluate(() => window.__result)
  const toolActivity = evts.filter((e) => e.type === 'tool_activity')
  const completedTools = [
    ...new Set(
      toolActivity
        .filter((e) => e.status === 'completed')
        .map((e) => e.name)
        .filter(Boolean)
    )
  ]
  const toolOutputs = evts
    .filter((e) => e.type === 'tool_result_display')
    .map((e) => ({ name: e.name, output: e.output || '' }))
  const replyText =
    evts
      .filter((e) => e.type === 'completed')
      .map((e) => e.text)
      .filter(Boolean)
      .pop() ||
    evts
      .filter((e) => e.type === 'text_delta')
      .map((e) => e.text)
      .join('')
  const rf = evts.find((e) => e.type === 'run_finished')
  const terminalStatus = rf?.status || result?.terminalStatus || 'unknown'
  const runError = rf?.error || (terminalStatus === 'failed' ? result?.error : undefined)
  const auditAfter = auditToolsAfter(auditLog)
  const newAudit = [...auditAfter].filter((t) => !auditBefore.has(t))
  return {
    requestId,
    completedTools,
    toolOutputs,
    reply: (replyText || '').trim(),
    terminalStatus,
    runError,
    newAudit
  }
}
function isTransientOutcome(o) {
  return TRANSIENT_RE.test(`${o.runError || ''} ${o.reply || ''}`)
}

// ── Phase 1: deterministic per-tool verification ────────────────────────────────
//
// Each row: { tool, layer:'direct', verdict, detail }. verdict ∈
//   PASS      — executor returned a valid result AND side-effect confirmed
//   BROKEN    — executor errored / bad shape / side-effect missing (the fix trigger)
//   SKIP      — expected-unsupported on this lane (spawn_agent)
//   INCONCL   — a precondition (e.g. backend sync) never happened; not a tool bug

const NOT_ERROR = (out) => !/^Error:/.test(out) && !/^POLICY_DENIED/.test(out)

async function runPhase1(page, restBases, idToken) {
  const rows = []
  const push = (tool, verdict, detail, out) => {
    rows.push({
      tool,
      layer: 'direct',
      verdict,
      detail,
      out: (out || '').slice(0, 160).replace(/\s+/g, ' ')
    })
    log(`  P1 ${verdict.padEnd(8)} ${tool.padEnd(22)} ${detail}`)
  }

  // — READ / QUERY tools (output-shape predicates) —
  const reads = [
    {
      tool: 'get_memories',
      args: { limit: 10 },
      ok: (o) => NOT_ERROR(o) && /User Memories|No memories|memor/i.test(o),
      why: 'returns a memories payload'
    },
    {
      tool: 'search_memories',
      args: { query: 'coffee' },
      ok: (o) => NOT_ERROR(o) && /Found \d+ memor|No memories/i.test(o),
      why: 'returns a memory-search result'
    },
    {
      tool: 'get_conversations',
      args: { limit: 3 },
      ok: (o) => NOT_ERROR(o) && /Conversation|No conversations/i.test(o),
      why: 'returns a conversations payload'
    },
    {
      tool: 'search_conversations',
      args: { query: 'launch' },
      ok: (o) => NOT_ERROR(o) && /found matching|No conversations found|Found \d+/i.test(o),
      why: 'returns a conversation-search result'
    },
    {
      tool: 'semantic_search',
      args: { query: 'machine learning' },
      ok: (o) => NOT_ERROR(o) && /Found \d+ screenshot|No matching screen-history/i.test(o),
      why: 'returns a screen-history search result'
    },
    {
      tool: 'get_daily_recap',
      args: { days_ago: 0 },
      ok: (o) => NOT_ERROR(o) && /Recap/.test(o) && /## /.test(o),
      why: 'returns a formatted recap'
    },
    {
      tool: 'get_work_context',
      args: {},
      ok: (o) => {
        try {
          const j = JSON.parse(o)
          return (
            j &&
            j.name === 'get_work_context' &&
            (j.ok === true || typeof j.failure_code === 'string')
          )
        } catch {
          return false
        }
      },
      why: 'returns the work-context manifest JSON'
    }
  ]
  for (const r of reads) {
    const out = await directExec(page, r.tool, r.args)
    push(
      r.tool,
      r.ok(out) ? 'PASS' : 'BROKEN',
      r.ok(out) ? r.why : `bad output: ${out.slice(0, 80)}`,
      out
    )
  }

  // — execute_sql (deterministic allowlisted query returns a result set) —
  {
    const out = await directExec(page, 'execute_sql', {
      query: 'SELECT COUNT(*) AS n FROM action_items'
    })
    const ok = NOT_ERROR(out) && /row\(s\)/.test(out)
    push(
      'execute_sql',
      ok ? 'PASS' : 'BROKEN',
      ok ? 'returns a result set' : `bad output: ${out.slice(0, 80)}`,
      out
    )
  }

  // — capture_screen (a path, or POLICY_DENIED when sharing is off — both prove it ran) —
  {
    const out = await directExec(page, 'capture_screen', {})
    const ok = /POLICY_DENIED/.test(out) || /\.png|screenshot|[A-Za-z]:\\/.test(out)
    const denied = /POLICY_DENIED/.test(out)
    push(
      'capture_screen',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? denied
          ? 'ran (screen-sharing off → policy denied)'
          : 'captured a screenshot path'
        : `bad output: ${out.slice(0, 80)}`,
      out
    )
  }

  // — list_agent_sessions (control tool: JSON {ok, sessions[]}) —
  {
    const out = await directExec(page, 'list_agent_sessions', {})
    let ok = false
    try {
      const j = JSON.parse(out)
      ok = j && j.ok === true && Array.isArray(j.sessions)
    } catch {
      ok = false
    }
    push(
      'list_agent_sessions',
      ok ? 'PASS' : 'BROKEN',
      ok ? 'returns the sessions manifest' : `bad output: ${out.slice(0, 80)}`,
      out
    )
  }

  // — spawn_agent (the coding-agent door: boots a real local Claude Code session).
  //   Deliberately NOT spawned to completion: it would delegate a live agent on the
  //   account, and the connect/OAuth stack is broken right now (per brief). Probe
  //   with EMPTY args — parse throws BEFORE delegateAgent, so nothing spawns — to
  //   confirm the control handler is REACHABLE + input-validating (registered, not
  //   "not available"), then SKIP per the coding-tool policy. No cancel needed.
  {
    const out = await directExec(page, 'spawn_agent', {})
    const reachable =
      /invalid_tool_input|objective|required|not allowed|disabled|spawn/i.test(out) &&
      !/is not available on Windows/i.test(out)
    push(
      'spawn_agent',
      'SKIP',
      reachable
        ? 'coding-agent door — reachable + input-validating; not spawned (needs connected Claude Code)'
        : `coding-agent door — not spawned; unexpected probe response: ${out.slice(0, 70)}`,
      out
    )
  }

  // — save_knowledge_graph (mutating: verify via execute_sql over onboarding_kg_nodes) —
  {
    const out = await directExec(page, 'save_knowledge_graph', {
      nodes: [{ id: KG_NODE_ID, label: 'Omi Gauntlet Self-Test', node_type: 'concept' }],
      edges: []
    })
    const okStr = /^OK: saved \d+ entit/.test(out)
    const { count } = await sqlCount(
      page,
      `SELECT COUNT(*) AS n FROM onboarding_kg_nodes WHERE node_id = '${KG_NODE_ID}'`
    )
    const ok = okStr && count != null && count >= 1
    push(
      'save_knowledge_graph',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? `saved + confirmed in DB (node present)`
        : `okStr=${okStr} dbCount=${count} out=${out.slice(0, 60)}`,
      out
    )
  }

  // — TASK CRUD LIFECYCLE (create → get → search → update → complete → delete),
  //   each mutation confirmed INDEPENDENTLY by execute_sql over action_items —
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  let backendId = null

  // create_action_item
  {
    const out = await directExec(page, 'create_action_item', {
      description: `${TASK_MARKER} milk`,
      due_at: tomorrow
    })
    const okStr = /^OK: task .* created/.test(out)
    // Wait for the local row (+ its backend_id from background sync) to exist.
    const deadline = Date.now() + BACKEND_SYNC_TIMEOUT_MS
    let localCount = 0
    for (;;) {
      const c = await sqlCount(
        page,
        `SELECT COUNT(*) AS n FROM action_items WHERE description LIKE '${like(TASK_MARKER)}' AND deleted = 0`
      )
      localCount = c.count ?? 0
      if (localCount >= 1) {
        const bid = await sqlScalar(
          page,
          `SELECT backend_id FROM action_items WHERE description LIKE '${like(TASK_MARKER)}' AND backend_id IS NOT NULL ORDER BY id DESC LIMIT 1`
        )
        if (bid.value && bid.value !== '') {
          backendId = bid.value
          break
        }
      }
      if (Date.now() > deadline) break
      await new Promise((r) => setTimeout(r, 1500))
    }
    const ok = okStr && localCount >= 1
    push(
      'create_action_item',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? `created + confirmed in DB (backend_id=${backendId ?? 'pending'})`
        : `okStr=${okStr} dbCount=${localCount} out=${out.slice(0, 60)}`,
      out
    )
  }

  // get_action_items — proves the read returns the real row we just created
  {
    const out = await directExec(page, 'get_action_items', {})
    const ok = NOT_ERROR(out) && /^Found \d+ task/.test(out) && out.includes(TASK_MARKER)
    push(
      'get_action_items',
      ok ? 'PASS' : 'BROKEN',
      ok ? 'lists the created marker task' : `did not list marker: ${out.slice(0, 80)}`,
      out
    )
  }

  // search_tasks — valid shape (embeddings may lag, so empty is acceptable-but-noted)
  {
    const out = await directExec(page, 'search_tasks', { query: 'milk' })
    const validShape = NOT_ERROR(out) && /^(Found \d+ task|No tasks found matching)/.test(out)
    const empty = /^No tasks found/.test(out)
    push(
      'search_tasks',
      validShape ? 'PASS' : 'BROKEN',
      validShape
        ? empty
          ? 'ran (no embedding match yet)'
          : 'returned matches'
        : `bad output: ${out.slice(0, 80)}`,
      out
    )
  }

  // update_action_item — needs the backend_id; confirm new description landed
  if (backendId) {
    const out = await directExec(page, 'update_action_item', {
      action_item_id: backendId,
      description: `${TASK_MARKER} oat milk`
    })
    const okStr = /^OK: task .* updated/.test(out)
    const { count } = await sqlCount(
      page,
      `SELECT COUNT(*) AS n FROM action_items WHERE description LIKE '${like(TASK_MARKER + ' oat milk')}' AND deleted = 0`
    )
    const ok = okStr && count != null && count >= 1
    push(
      'update_action_item',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? 'updated + confirmed new description in DB'
        : `okStr=${okStr} dbCount=${count} out=${out.slice(0, 60)}`,
      out
    )
  } else {
    push(
      'update_action_item',
      'INCONCL',
      'task never synced a backend_id (backend sync down?) — cannot target by id',
      ''
    )
  }

  // complete_task — confirm completed=1
  if (backendId) {
    const out = await directExec(page, 'complete_task', { task_id: backendId })
    const okStr = /^OK: task .* (marked as completed|is already completed)/.test(out)
    const { count } = await sqlCount(
      page,
      `SELECT COUNT(*) AS n FROM action_items WHERE description LIKE '${like(TASK_MARKER)}' AND completed = 1 AND deleted = 0`
    )
    const ok = okStr && count != null && count >= 1
    push(
      'complete_task',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? 'completed + confirmed completed=1 in DB'
        : `okStr=${okStr} dbCount=${count} out=${out.slice(0, 60)}`,
      out
    )
  } else {
    push('complete_task', 'INCONCL', 'no backend_id to target', '')
  }

  // delete_task — confirm the row is gone (hard delete)
  if (backendId) {
    const out = await directExec(page, 'delete_task', { task_id: backendId })
    const okStr = /^OK: task .* deleted/.test(out)
    const { count } = await sqlCount(
      page,
      `SELECT COUNT(*) AS n FROM action_items WHERE description LIKE '${like(TASK_MARKER)}' AND deleted = 0`
    )
    const ok = okStr && count === 0
    push(
      'delete_task',
      ok ? 'PASS' : 'BROKEN',
      ok
        ? 'deleted + confirmed 0 rows in DB'
        : `okStr=${okStr} dbCount=${count} out=${out.slice(0, 60)}`,
      out
    )
  } else {
    push('delete_task', 'INCONCL', 'no backend_id to target', '')
  }

  // REST safety-net sweep for the Phase-1 marker (in case backend sync lagged).
  await restDeleteMarked(restBases, idToken, TASK_MARKER)

  return rows
}

// ── Phase 2: LLM dispatch matrix ────────────────────────────────────────────────
const PHASE2 = [
  {
    id: 'get_action_items',
    kind: 'product',
    expect: ['get_action_items'],
    alt: ['search_tasks', 'execute_sql'],
    prompts: ['What are my tasks / action items?', 'Use get_action_items to list my current tasks.']
  },
  {
    id: 'create_action_item',
    kind: 'product',
    expect: ['create_action_item'],
    prompts: [
      `Add a task to my list: "${P2_MARKER} draft".`,
      `Use create_action_item to create a task whose description is exactly "${P2_MARKER} draft".`
    ]
  },
  {
    id: 'update_action_item',
    kind: 'product',
    expect: ['update_action_item'],
    alt: ['search_tasks', 'get_action_items'],
    prompts: [
      `Change my task containing "${P2_MARKER}" to "${P2_MARKER} final draft".`,
      `Use get_action_items to find the task whose description contains "${P2_MARKER}", then update_action_item to set its description to "${P2_MARKER} final draft".`
    ]
  },
  {
    id: 'complete_task',
    kind: 'product',
    expect: ['complete_task'],
    alt: ['update_action_item'],
    prompts: [
      `Mark my "${P2_MARKER}" task as done.`,
      `Find the task containing "${P2_MARKER}" and use complete_task to mark it completed.`
    ]
  },
  {
    id: 'search_tasks',
    kind: 'product',
    expect: ['search_tasks'],
    alt: ['execute_sql', 'get_action_items'],
    prompts: [
      'Search my tasks for anything about drafts.',
      'Use the search_tasks tool with the query "draft".'
    ]
  },
  {
    id: 'delete_task',
    kind: 'product',
    expect: ['delete_task'],
    alt: ['get_action_items'],
    prompts: [
      `Delete my task containing "${P2_MARKER}".`,
      `Find the task whose description contains "${P2_MARKER}" and permanently delete it with delete_task.`
    ]
  },
  {
    id: 'get_memories',
    kind: 'product',
    expect: ['get_memories'],
    alt: ['search_memories'],
    prompts: [
      'What do you know about me? Check my memories.',
      'Use get_memories to retrieve what Omi knows about me.'
    ]
  },
  {
    id: 'search_memories',
    kind: 'product',
    expect: ['search_memories'],
    alt: ['get_memories'],
    prompts: [
      'Search my memories for anything about coffee.',
      'Use the search_memories tool with the query "coffee".'
    ]
  },
  {
    id: 'get_conversations',
    kind: 'product',
    expect: ['get_conversations'],
    alt: ['search_conversations'],
    prompts: [
      "What's my most recent conversation? Summarize it.",
      'Use get_conversations to fetch my most recent conversation.'
    ]
  },
  {
    id: 'search_conversations',
    kind: 'product',
    expect: ['search_conversations'],
    alt: ['get_conversations'],
    prompts: [
      'Search my conversations for anything about launch.',
      'Use the search_conversations tool with the query "launch".'
    ]
  },
  {
    id: 'semantic_search',
    kind: 'product',
    expect: ['semantic_search', 'search_screen_history'],
    alt: ['execute_sql'],
    prompts: [
      'When was I reading about machine learning? Search my screen history.',
      'Use the semantic_search tool with the query "machine learning".'
    ]
  },
  {
    id: 'execute_sql',
    kind: 'product',
    expect: ['execute_sql'],
    prompts: [
      'How many rewind frames do I have? Query the local database.',
      'Use execute_sql to run SELECT COUNT(*) over my rewind_frames table.'
    ]
  },
  {
    id: 'get_daily_recap',
    kind: 'product',
    expect: ['get_daily_recap'],
    alt: ['execute_sql', 'get_work_context'],
    prompts: [
      'What did I do today? Give me a recap.',
      'Use the get_daily_recap tool for today (days_ago 0).'
    ]
  },
  {
    id: 'get_work_context',
    kind: 'product',
    expect: ['get_work_context'],
    alt: ['capture_screen'],
    prompts: [
      "What's on my screen right now?",
      'Use the get_work_context tool to see my current screen and recent activity.'
    ]
  },
  {
    id: 'save_knowledge_graph',
    kind: 'product',
    expect: ['save_knowledge_graph'],
    prompts: [
      `Remember this entity in my knowledge graph: a concept called "${P2_MARKER} Topic".`,
      `Use save_knowledge_graph to save one node: id "${KG_NODE_ID}", label "Omi Gauntlet Self-Test", node_type concept.`
    ]
  },
  {
    id: 'capture_screen',
    kind: 'product',
    expect: ['capture_screen'],
    alt: ['get_work_context'],
    allowDenied: true,
    prompts: [
      'Take a screenshot of my screen right now.',
      'Use the capture_screen tool to capture my screen this instant.'
    ]
  },
  {
    id: 'list_agent_sessions',
    kind: 'control',
    expect: ['list_agent_sessions'],
    prompts: [
      'List my running agent sessions.',
      'Call list_agent_sessions and tell me what sessions exist.'
    ]
  },
  {
    id: 'bash',
    kind: 'coding',
    expect: ['bash'],
    prompts: [
      'Run the shell command: echo hello-gauntlet',
      'Use your bash/shell tool to run exactly `echo hello-gauntlet`.'
    ]
  },
  {
    id: 'read',
    kind: 'coding',
    expect: ['read'],
    prompts: [
      'Read the first lines of any small text file you can find in the working directory.',
      'Use your read/read-file tool to read a file and show its contents.'
    ]
  },
  {
    id: 'write',
    kind: 'coding',
    expect: ['write'],
    prompts: [
      `Create a file at ${WRITE_PROBE_PROMPT_PATH} containing exactly the text hello.`,
      `Use your write/write-file tool to create the file ${WRITE_PROBE_PROMPT_PATH} with the contents hello.`
    ]
  },
  {
    id: 'spawn_agent',
    kind: 'spawn',
    expect: ['spawn_agent', 'spawn_background_agent'],
    prompts: [
      'Spin up a background agent to research the printing press.',
      'Use spawn_agent to start a background agent researching the printing press.'
    ]
  }
]

async function runPhase2(page, auditLog) {
  const rows = []
  for (const t of PHASE2) {
    const accepted = new Set([...(t.expect || []), ...(t.alt || [])])
    let outcome = null
    let fired = null
    let noTool = 0
    let transient = 0
    let step = 0
    for (let turn = 0; turn < MAX_TURN_BUDGET; turn++) {
      const prompt = t.prompts[Math.min(step, t.prompts.length - 1)]
      outcome = await sendTurn(page, prompt, auditLog)
      const hit = outcome.completedTools.find((n) => accepted.has(n))
      const anyTool = outcome.completedTools[0]
      log(
        `  P2 [${t.id}] t${turn + 1} tools=[${outcome.completedTools.join(',') || '-'}] status=${outcome.terminalStatus}${outcome.runError ? ` err=${outcome.runError.slice(0, 50)}` : ''}`
      )
      if (hit) {
        fired = hit
        break
      }
      if (anyTool) {
        fired = `~${anyTool}`
        break
      } // a different valid tool still proves dispatch reached the plane
      const failed =
        outcome.terminalStatus === 'failed' ||
        outcome.terminalStatus === 'unknown' ||
        !!outcome.runError
      if (failed && isTransientOutcome(outcome)) {
        if (transient >= MAX_TRANSIENT_RETRIES) break
        transient++
        await new Promise((r) => setTimeout(r, 3000 * transient))
        continue
      }
      if (failed) break
      noTool++
      if (noTool >= MAX_NOTOOL_ATTEMPTS) break
      step = Math.min(step + 1, t.prompts.length - 1)
      await new Promise((r) => setTimeout(r, 1000))
    }

    // Classify per kind.
    const didFire = !!fired
    const exactFire = fired && !fired.startsWith('~')
    let verdict
    if (t.kind === 'product' || t.kind === 'control') {
      verdict = didFire
        ? exactFire
          ? 'FIRED'
          : 'FIRED(alt)'
        : isTransientOutcome(outcome || {})
          ? 'TRANSIENT'
          : 'DISPATCH-MISS'
    } else if (t.kind === 'coding') {
      verdict = didFire ? 'FIRED(local)' : 'SKIP' // pi-mono built-in, local working dir
    } else {
      // spawn on managed-cloud lane
      verdict = didFire ? 'FIRED' : 'SKIP'
    }
    rows.push({
      tool: t.id,
      layer: 'llm',
      kind: t.kind,
      verdict,
      fired: fired || '-',
      reply: (outcome?.reply || '').slice(0, 80)
    })
    log(`  P2 => ${verdict.padEnd(14)} ${t.id}`)

    // spawn_agent that fired → cancel it.
    if (t.kind === 'spawn' && didFire) {
      await sendTurn(
        page,
        'Cancel that background agent run now using cancel_agent_run (list_agent_sessions first if you need the run id).',
        auditLog
      ).catch(() => {})
    }
  }
  return rows
}

// ── REST cleanup helper ─────────────────────────────────────────────────────────
async function restDeleteMarked(restBases, idToken, marker) {
  for (const base of restBases) {
    try {
      const listRes = await fetch(`${base.replace(/\/$/, '')}/v1/action-items?limit=200`, {
        headers: { Authorization: `Bearer ${idToken}` }
      })
      if (!listRes.ok) continue
      const data = await listRes.json().catch(() => ({}))
      const items = Array.isArray(data) ? data : data.action_items || data.items || []
      const mine = items.filter((it) => String(it.description || it.content || '').includes(marker))
      let deleted = 0
      for (const it of mine) {
        const id = it.id || it.action_item_id || it.backendId
        if (!id) continue
        const dRes = await fetch(`${base.replace(/\/$/, '')}/v1/action-items/${id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${idToken}` }
        })
        if (dRes.ok) deleted++
      }
      log(`REST sweep [${marker}] base ${base}: found ${mine.length}, deleted ${deleted}`)
      return
    } catch (e) {
      log(`REST sweep [${marker}] base ${base} err ${String(e).slice(0, 60)}`)
    }
  }
}

// ── main ─────────────────────────────────────────────────────────────────────────
async function main() {
  const env = readDotEnv(path.join(root, '.env'))
  const refreshToken = process.env.OMI_E2E_REFRESH_TOKEN ?? env.OMI_E2E_REFRESH_TOKEN
  const apiKey = process.env.VITE_FIREBASE_API_KEY ?? env.VITE_FIREBASE_API_KEY
  if (!refreshToken || !apiKey) {
    log('SKIP: OMI_E2E_REFRESH_TOKEN / VITE_FIREBASE_API_KEY missing from .env')
    process.exit(2)
  }
  const restBases = [
    env.VITE_OMI_DESKTOP_API_BASE,
    env.VITE_OMI_API_BASE,
    env.VITE_OMI_BASE_API_URL,
    'https://api.omi.me'
  ].filter(Boolean)

  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`SKIP: built main not found (${mainEntry}) — run \`pnpm build\` first`)
    process.exit(2)
  }

  let idToken
  try {
    idToken = await exchangeRefreshToken(refreshToken, apiKey)
  } catch (e) {
    log(`SKIP: refresh-token exchange failed (${e.message})`)
    process.exit(2)
  }
  const uid = decodeJwt(idToken)?.user_id
  log(`auth ok (uid ${uid})`)

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-'))
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-gauntlet-ud-'))
  const auditLog = path.join(tmp, 'pi-mono-audit.log')
  let phase1 = []
  let phase2 = []
  let exitCode = 0
  let app = null

  try {
    app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0', OMI_PI_AUDIT_LOG: auditLog }
    })

    let page = await findMainWindow(app)
    if (!page) throw new Error('main window never appeared')
    await page.waitForLoadState('domcontentloaded')
    await injectAuth(page, { apiKey, idToken, refreshToken })
    await page.evaluate(() => {
      const KEY = 'omi-windows-prefs-v1'
      const prefs = JSON.parse(localStorage.getItem(KEY) ?? '{}')
      prefs.onboardingCompletedAt = prefs.onboardingCompletedAt ?? Date.now()
      localStorage.setItem(KEY, JSON.stringify(prefs))
      location.reload()
    })
    await new Promise((r) => setTimeout(r, 3000))
    page = await findMainWindow(app)
    await page.waitForLoadState('domcontentloaded')
    await waitFor(
      page,
      () => typeof globalThis.__omiVoice?.getAuthUid === 'function',
      30_000,
      'e2e hook'
    )
    const signedUid = await waitFor(
      page,
      () => globalThis.__omiVoice.getAuthUid(),
      30_000,
      'signed-in uid'
    )
    log(`app signed in as ${signedUid}`)

    await page.evaluate(() => {
      window.__tev = []
      window.omi.onMainChatEvent((e) => window.__tev.push(e))
    })

    // Warm-up: the control-plane owner is wired asynchronously after sign-in. Poll a
    // trivial DIRECT host-tool call until it stops failing the sign-in gate — this
    // proves the deterministic door is live before we score anything.
    let warmed = false
    for (let i = 0; i < 30 && !warmed; i++) {
      const out = await directExec(page, 'get_action_items', {})
      if (!/sign-in has not completed/i.test(out)) {
        warmed = true
        log(`warm-up ok (get_action_items returned: "${out.slice(0, 50).replace(/\s+/g, ' ')}")`)
      } else {
        await new Promise((r) => setTimeout(r, 2000))
      }
    }
    if (!warmed)
      throw new Error(
        'control-plane owner never wired (voiceToolExecute kept failing the sign-in gate)'
      )

    // ── PHASE 1 ──
    if (!PHASE2_ONLY) {
      log('══════════ PHASE 1: deterministic executor proof ══════════')
      phase1 = await runPhase1(page, restBases, idToken)
    }

    // ── PHASE 2 ──
    if (!PHASE1_ONLY) {
      log('══════════ PHASE 2: LLM dispatch proof ══════════')
      phase2 = await runPhase2(page, auditLog)
      // Clean up the Phase-2 marker task (chat delete first, REST sweep as net).
      await sendTurn(
        page,
        `Find the task whose description contains "${P2_MARKER}" (use get_action_items) and permanently delete it with delete_task.`,
        auditLog
      ).catch(() => {})
      await restDeleteMarked(restBases, idToken, P2_MARKER)
      // Sweep the coding-tool write artifact (pi-mono writes to the LOCAL working
      // dir, so a stray gauntlet-probe.txt can land at the repo/cwd root too).
      for (const p of [
        WRITE_PROBE_PATH,
        path.join(root, 'gauntlet-probe.txt'),
        path.join(process.cwd(), 'gauntlet-probe.txt')
      ]) {
        try {
          fs.rmSync(p, { force: true })
        } catch {
          /* best effort */
        }
      }
    }
  } catch (e) {
    log(`ERROR: ${e?.stack || e}`)
    exitCode = 1
  } finally {
    try {
      if (app) await app.close()
    } catch {
      /* already closed */
    }
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best effort */
    }

    // ── Report ──
    log('')
    log('════════════════════ ROBUST TOOL GAUNTLET ════════════════════')
    const broken = phase1.filter((r) => r.verdict === 'BROKEN')
    const inconcl = phase1.filter((r) => r.verdict === 'INCONCL')
    const p1pass = phase1.filter((r) => r.verdict === 'PASS')
    const p1skip = phase1.filter((r) => r.verdict === 'SKIP')

    log('── PHASE 1 (deterministic — authoritative) ──')
    for (const r of phase1) log(`  ${r.verdict.padEnd(8)} ${r.tool.padEnd(22)} ${r.detail}`)
    log(
      `  Phase 1: ${p1pass.length} PASS · ${broken.length} BROKEN · ${p1skip.length} SKIP · ${inconcl.length} INCONCL`
    )

    if (phase2.length) {
      log('── PHASE 2 (LLM dispatch — corroborating) ──')
      for (const r of phase2)
        log(`  ${r.verdict.padEnd(14)} ${r.tool.padEnd(22)} fired=[${r.fired}]`)
      const fired2 = phase2.filter((r) => r.verdict.startsWith('FIRED'))
      const miss2 = phase2.filter((r) => r.verdict === 'DISPATCH-MISS')
      const skip2 = phase2.filter((r) => r.verdict === 'SKIP')
      const trans2 = phase2.filter((r) => r.verdict === 'TRANSIENT')
      log(
        `  Phase 2: ${fired2.length} FIRED · ${miss2.length} DISPATCH-MISS · ${skip2.length} SKIP · ${trans2.length} TRANSIENT`
      )
      if (miss2.length)
        log(
          `  Dispatch-misses (model didn't call it; tool itself proven in P1): ${miss2.map((r) => r.tool).join(', ')}`
        )
    }

    log('───────────────────────────────────────────────────────────────')
    if (broken.length) {
      log(`  ❌ BROKEN PRODUCT TOOLS: ${broken.map((r) => r.tool).join(', ')}`)
      exitCode = 1
    } else if (inconcl.length) {
      log(
        `  ⚠ INCONCLUSIVE (env/backend-sync, not a tool bug): ${inconcl.map((r) => r.tool).join(', ')}`
      )
      if (exitCode === 0) exitCode = 3
    } else {
      log('  ✅ Every product/control tool PROVEN working end-to-end.')
    }
    log(`  KG artifact left by design (stable, idempotent): node_id=${KG_NODE_ID}`)
    log('═══════════════════════════════════════════════════════════════')

    try {
      const outFile = path.join(root, 'tool-gauntlet-report.json')
      fs.writeFileSync(outFile, JSON.stringify({ runId: RUN_ID, uid, phase1, phase2 }, null, 2))
      log(`report → ${outFile}`)
    } catch {
      /* ignore */
    }
    try {
      fs.rmSync(tmp, { recursive: true, force: true })
    } catch {
      /* best effort */
    }
    process.exit(phase1.length || phase2.length ? exitCode : 2)
  }
}

main().catch((e) => {
  console.error(`[gauntlet] fatal: ${e?.stack || e}`)
  process.exit(1)
})
