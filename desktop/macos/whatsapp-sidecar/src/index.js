// Omi WhatsApp sidecar — a local-only Node process wrapping Baileys (the unofficial
// WhatsApp Web "Linked Devices" protocol). Spawned and owned by the desktop app's
// WhatsAppSendService; never exposed beyond 127.0.0.1.
//
// This connects a PERSONAL WhatsApp account through an unofficial library. It must never
// initiate anything on its own: every send is an explicit HTTP request from the app, which
// itself gates automated sends behind the AI Clone kill switch + per-contact modes.
//
// HTTP API (all JSON):
//   GET  /health              → { ok, state }
//   GET  /link/status         → { state, qrDataUrl?, phone? }   state: unlinked | connecting |
//                                waiting_qr | linked | logged_out
//   POST /link/start          → begin linking (or resume a saved session); returns /link/status
//   POST /send {to, text}     → send a text message; `to` is digits or a full JID
//   POST /read {to}           → mark the latest incoming message from `to` as read (blue ticks)
//   POST /presence {to, state}→ show "typing…" to `to` (state: composing | paused)
//   GET  /events?since=N      → { events: [{seq, phone, fromMe, text, timestamp, senderName}], latest }
//   GET  /resolve?name=X      → { phone, jid, name } or 404 — display-name → JID lookup
//   POST /logout              → unlink + clear the saved session
//
// Session persists under OMI_WA_SESSION_DIR (multi-file auth state), so linking survives
// restarts. The process tethers itself to the parent: it exits when stdin closes.

import { createServer } from 'node:http'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'
import pino from 'pino'
import QRCode from 'qrcode'
import * as baileysModule from '@whiskeysockets/baileys'

const baileys = baileysModule.default?.makeWASocket ? baileysModule.default : baileysModule
const makeWASocket = baileys.makeWASocket ?? baileys.default
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = baileys

const PORT = Number(process.env.OMI_WA_PORT || 47790)
const TOKEN = process.env.OMI_WA_TOKEN || ''
const SESSION_DIR =
  process.env.OMI_WA_SESSION_DIR ||
  join(homedir(), 'Library', 'Application Support', 'Omi', 'whatsapp-session')
const CONTACTS_FILE = join(SESSION_DIR, 'contacts.json')
const MAX_EVENTS = 500

const logger = pino({ level: process.env.OMI_WA_LOG_LEVEL || 'warn' })

// ---------------------------------------------------------------------------
// State

/** @type {'unlinked'|'connecting'|'waiting_qr'|'linked'|'logged_out'} */
let state = 'unlinked'
let sock = null
let latestQrDataUrl = null
let linkedPhone = null
let reconnectAttempts = 0
let startPromise = null
let shuttingDown = false

// Incoming-message ring buffer, consumed by the app via GET /events?since=<seq>.
let eventSeq = 0
const events = []

// Latest incoming message key per 1:1 jid, so POST /read can ack ("blue tick") it.
/** @type {Map<string, object>} */
const lastIncomingKeyByJid = new Map()

// Display-name → JID map for resolving imported contacts to real numbers. Seeded from the
// initial history sync, then kept fresh from contact upserts and message push-names.
/** @type {Map<string, {jid: string, name: string}>} */
const contactsByJid = new Map()

function loadContacts() {
  try {
    if (existsSync(CONTACTS_FILE)) {
      for (const entry of JSON.parse(readFileSync(CONTACTS_FILE, 'utf8'))) {
        if (entry?.jid && entry?.name) contactsByJid.set(entry.jid, entry)
      }
    }
  } catch (err) {
    logger.warn({ err: String(err) }, 'failed to load contacts cache')
  }
}

let contactsSaveTimer = null
function scheduleSaveContacts() {
  if (contactsSaveTimer) return
  contactsSaveTimer = setTimeout(() => {
    contactsSaveTimer = null
    try {
      mkdirSync(SESSION_DIR, { recursive: true })
      writeFileSync(CONTACTS_FILE, JSON.stringify([...contactsByJid.values()]))
    } catch (err) {
      logger.warn({ err: String(err) }, 'failed to save contacts cache')
    }
  }, 2000)
}

function rememberContact(jid, name) {
  if (!jid || !name || !jid.endsWith('@s.whatsapp.net')) return
  const trimmed = String(name).trim()
  if (!trimmed) return
  const existing = contactsByJid.get(jid)
  if (existing?.name === trimmed) return
  contactsByJid.set(jid, { jid, name: trimmed })
  scheduleSaveContacts()
}

function phoneFromJid(jid) {
  return String(jid || '').split('@')[0].split(':')[0]
}

// ---------------------------------------------------------------------------
// Baileys socket lifecycle

function hasSavedSession() {
  return existsSync(join(SESSION_DIR, 'creds.json'))
}

async function startSocket() {
  if (startPromise) return startPromise
  startPromise = (async () => {
    try {
      state = 'connecting'
      latestQrDataUrl = null
      mkdirSync(SESSION_DIR, { recursive: true })
      const { state: authState, saveCreds } = await useMultiFileAuthState(SESSION_DIR)
      const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }))

      sock = makeWASocket({
        version,
        auth: authState,
        logger: logger.child({ module: 'baileys' }),
        printQRInTerminal: false,
        markOnlineOnConnect: false,
        syncFullHistory: false,
        generateHighQualityLinkPreview: false,
        browser: ['Omi Desktop', 'Desktop', '1.0.0'],
      })

      sock.ev.on('creds.update', saveCreds)

      sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update
        if (qr) {
          try {
            latestQrDataUrl = await QRCode.toDataURL(qr, { margin: 1, width: 400 })
            state = 'waiting_qr'
          } catch (err) {
            logger.warn({ err: String(err) }, 'QR encode failed')
          }
        }
        if (connection === 'open') {
          state = 'linked'
          latestQrDataUrl = null
          reconnectAttempts = 0
          linkedPhone = phoneFromJid(sock?.user?.id)
          logger.info({ phone: linkedPhone }, 'linked')
        }
        if (connection === 'close') {
          const statusCode = lastDisconnect?.error?.output?.statusCode
          const loggedOut = statusCode === DisconnectReason.loggedOut
          sock = null
          startPromise = null
          if (shuttingDown || shuttingDownSocketOnly) return
          if (loggedOut) {
            // The phone unlinked this device — the saved session is dead. Clear it so the
            // next /link/start produces a fresh QR instead of a reconnect loop.
            clearSession()
            state = 'logged_out'
            linkedPhone = null
            logger.info('logged out — session cleared')
            return
          }
          // Transient close (network, server restart, QR timeout). Retry with backoff, but
          // only keep retrying indefinitely when a saved session exists; a pending QR link
          // gets a few attempts and then goes back to unlinked (the app can restart it).
          const resumable = hasSavedSession()
          reconnectAttempts += 1
          if (!resumable && reconnectAttempts > 3) {
            state = 'unlinked'
            latestQrDataUrl = null
            logger.info('link attempt expired')
            return
          }
          state = 'connecting'
          const delay = Math.min(30000, 1000 * 2 ** Math.min(reconnectAttempts, 5))
          logger.info({ statusCode, delay }, 'connection closed — reconnecting')
          setTimeout(() => {
            if (!shuttingDown && !sock) startSocket().catch(() => {})
          }, delay)
        }
      })

      // Initial history sync — the richest source of jid→name pairs.
      sock.ev.on('messaging-history.set', ({ contacts }) => {
        for (const c of contacts || []) rememberContact(c.id, c.name || c.notify || c.verifiedName)
      })
      sock.ev.on('contacts.upsert', (contacts) => {
        for (const c of contacts || []) rememberContact(c.id, c.name || c.notify || c.verifiedName)
      })
      sock.ev.on('contacts.update', (updates) => {
        for (const c of updates || []) {
          if (c.id && (c.name || c.notify)) rememberContact(c.id, c.name || c.notify)
        }
      })
      sock.ev.on('chats.upsert', (chats) => {
        for (const c of chats || []) rememberContact(c.id, c.name)
      })

      sock.ev.on('messages.upsert', ({ messages, type }) => {
        if (type !== 'notify' && type !== 'append') return
        for (const msg of messages || []) {
          try {
            ingestMessage(msg)
          } catch (err) {
            logger.warn({ err: String(err) }, 'failed to ingest message')
          }
        }
      })
    } catch (err) {
      logger.error({ err: String(err) }, 'startSocket failed')
      sock = null
      startPromise = null
      state = hasSavedSession() ? 'connecting' : 'unlinked'
      throw err
    }
  })()
  return startPromise
}

function extractText(message) {
  if (!message) return null
  // Unwrap the containers WhatsApp nests real content in.
  const inner =
    message.ephemeralMessage?.message ||
    message.viewOnceMessage?.message ||
    message.viewOnceMessageV2?.message ||
    message.documentWithCaptionMessage?.message ||
    message
  return (
    inner.conversation ||
    inner.extendedTextMessage?.text ||
    inner.imageMessage?.caption ||
    inner.videoMessage?.caption ||
    null
  )
}

function ingestMessage(msg) {
  const jid = msg.key?.remoteJid
  // Direct (1:1) chats only — never groups, broadcasts, or status updates.
  if (!jid || !jid.endsWith('@s.whatsapp.net')) return
  const text = extractText(msg.message)
  if (!text) return
  const fromMe = !!msg.key?.fromMe
  if (!fromMe && msg.pushName) rememberContact(jid, msg.pushName)
  if (!fromMe && msg.key?.id) lastIncomingKeyByJid.set(jid, msg.key)
  eventSeq += 1
  events.push({
    seq: eventSeq,
    jid,
    phone: phoneFromJid(jid),
    fromMe,
    text,
    timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
    senderName: fromMe ? null : msg.pushName || contactsByJid.get(jid)?.name || null,
  })
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS)
}

function clearSession() {
  try {
    rmSync(SESSION_DIR, { recursive: true, force: true })
  } catch (err) {
    logger.warn({ err: String(err) }, 'failed to clear session dir')
  }
}

// ---------------------------------------------------------------------------
// HTTP helpers

function sendJson(res, status, body) {
  const data = JSON.stringify(body)
  res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) })
  res.end(data)
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = ''
    req.on('data', (chunk) => {
      raw += chunk
      if (raw.length > 1_000_000) reject(new Error('body too large'))
    })
    req.on('end', () => {
      if (!raw) return resolve({})
      try {
        resolve(JSON.parse(raw))
      } catch {
        reject(new Error('invalid JSON body'))
      }
    })
    req.on('error', reject)
  })
}

function linkStatusBody() {
  return {
    state,
    qrDataUrl: state === 'waiting_qr' ? latestQrDataUrl : null,
    phone: state === 'linked' ? linkedPhone : null,
  }
}

function normalizeSendTarget(to) {
  const raw = String(to || '').trim()
  if (!raw) return null
  if (raw.includes('@')) return raw.endsWith('@s.whatsapp.net') ? raw : null
  const digits = raw.replace(/[\s()+\-.]/g, '')
  if (!/^\d{5,20}$/.test(digits)) return null
  return `${digits}@s.whatsapp.net`
}

function resolveByName(name) {
  const needle = String(name || '').trim().toLowerCase()
  if (!needle) return null
  const all = [...contactsByJid.values()]
  const exact = all.filter((c) => c.name.toLowerCase() === needle)
  if (exact.length === 1) return exact[0]
  if (exact.length > 1) return null // ambiguous — refuse rather than guess
  const partial = all.filter(
    (c) => c.name.toLowerCase().startsWith(needle) || needle.startsWith(c.name.toLowerCase())
  )
  return partial.length === 1 ? partial[0] : null
}

// ---------------------------------------------------------------------------
// HTTP server

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`)
  if (TOKEN && req.headers['x-omi-token'] !== TOKEN) {
    return sendJson(res, 401, { error: 'unauthorized' })
  }

  try {
    if (req.method === 'GET' && url.pathname === '/health') {
      return sendJson(res, 200, { ok: true, state })
    }

    if (req.method === 'GET' && url.pathname === '/link/status') {
      return sendJson(res, 200, linkStatusBody())
    }

    if (req.method === 'POST' && url.pathname === '/link/start') {
      if (state !== 'linked' && !sock) {
        startSocket().catch((err) => logger.warn({ err: String(err) }, 'link start failed'))
        // Give Baileys a moment so the first status poll usually already has the QR.
        await new Promise((r) => setTimeout(r, 1500))
      }
      return sendJson(res, 200, linkStatusBody())
    }

    if (req.method === 'POST' && url.pathname === '/send') {
      if (state !== 'linked' || !sock) {
        return sendJson(res, 409, { error: 'not linked — scan the QR code first' })
      }
      const body = await readBody(req)
      const jid = normalizeSendTarget(body.to)
      const text = String(body.text || '').trim()
      if (!jid) return sendJson(res, 400, { error: 'invalid "to" — need digits or a @s.whatsapp.net JID' })
      if (!text) return sendJson(res, 400, { error: 'empty "text"' })
      await sock.sendMessage(jid, { text })
      return sendJson(res, 200, { sent: true, jid, phone: phoneFromJid(jid) })
    }

    if (req.method === 'POST' && url.pathname === '/read') {
      if (state !== 'linked' || !sock) {
        return sendJson(res, 409, { error: 'not linked' })
      }
      const body = await readBody(req)
      const jid = normalizeSendTarget(body.to)
      if (!jid) return sendJson(res, 400, { error: 'invalid "to"' })
      const key = lastIncomingKeyByJid.get(jid)
      if (!key) return sendJson(res, 200, { read: false, reason: 'no tracked incoming message' })
      await sock.readMessages([key])
      return sendJson(res, 200, { read: true, jid })
    }

    if (req.method === 'POST' && url.pathname === '/presence') {
      if (state !== 'linked' || !sock) {
        return sendJson(res, 409, { error: 'not linked' })
      }
      const body = await readBody(req)
      const jid = normalizeSendTarget(body.to)
      if (!jid) return sendJson(res, 400, { error: 'invalid "to"' })
      const presence = body.state === 'composing' ? 'composing' : 'paused'
      await sock.sendPresenceUpdate(presence, jid)
      return sendJson(res, 200, { presence, jid })
    }

    if (req.method === 'GET' && url.pathname === '/events') {
      const since = Number(url.searchParams.get('since') || 0)
      return sendJson(res, 200, {
        events: events.filter((e) => e.seq > since),
        latest: eventSeq,
        state,
      })
    }

    if (req.method === 'GET' && url.pathname === '/resolve') {
      const match = resolveByName(url.searchParams.get('name'))
      if (!match) return sendJson(res, 404, { error: 'no unambiguous contact match' })
      return sendJson(res, 200, { jid: match.jid, phone: phoneFromJid(match.jid), name: match.name })
    }

    if (req.method === 'POST' && url.pathname === '/logout') {
      shuttingDownSocketOnly = true
      try {
        await sock?.logout()
      } catch (err) {
        logger.warn({ err: String(err) }, 'logout call failed (clearing session anyway)')
      }
      shuttingDownSocketOnly = false
      sock = null
      startPromise = null
      clearSession()
      state = 'unlinked'
      linkedPhone = null
      latestQrDataUrl = null
      return sendJson(res, 200, linkStatusBody())
    }

    return sendJson(res, 404, { error: 'not found' })
  } catch (err) {
    logger.error({ err: String(err) }, 'request failed')
    return sendJson(res, 500, { error: String(err?.message || err) })
  }
})

// Suppresses the reconnect handler while an intentional logout tears the socket down.
let shuttingDownSocketOnly = false

server.listen(PORT, '127.0.0.1', () => {
  loadContacts()
  // Announce readiness on stdout (single JSON line) so the spawning app can wait for it.
  process.stdout.write(JSON.stringify({ type: 'ready', port: PORT, state }) + '\n')
  // Resume automatically when a saved session exists — no QR needed after first link.
  if (hasSavedSession()) {
    startSocket().catch((err) => logger.warn({ err: String(err) }, 'session resume failed'))
  }
})

server.on('error', (err) => {
  process.stdout.write(JSON.stringify({ type: 'error', error: String(err?.message || err) }) + '\n')
  process.exit(1)
})

// ---------------------------------------------------------------------------
// Parent tether — never outlive the app that spawned us.

function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  try {
    sock?.end?.(undefined)
  } catch {}
  try {
    server.close()
  } catch {}
  // Hard exit shortly after — Baileys keeps sockets/timers alive otherwise.
  setTimeout(() => process.exit(code), 250).unref()
}

process.stdin.resume()
process.stdin.on('end', () => shutdown(0))
process.stdin.on('close', () => shutdown(0))
process.stdin.on('error', () => shutdown(0))

// Belt-and-suspenders for the stdin tether: if the spawning app passed its PID, poll it and
// exit when it disappears (covers pipe semantics edge cases so we never orphan).
const parentPid = Number(process.env.OMI_WA_PARENT_PID || 0)
if (parentPid > 0) {
  setInterval(() => {
    try {
      process.kill(parentPid, 0)
    } catch {
      shutdown(0)
    }
  }, 5000).unref()
  // unref'd so this timer never keeps the process alive on its own; shutdown() handles exit.
}
process.on('SIGTERM', () => shutdown(0))
process.on('SIGINT', () => shutdown(0))
process.on('uncaughtException', (err) => {
  logger.error({ err: String(err?.stack || err) }, 'uncaught exception')
})
process.on('unhandledRejection', (err) => {
  logger.error({ err: String(err) }, 'unhandled rejection')
})
