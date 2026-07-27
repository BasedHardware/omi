#!/usr/bin/env node
/**
 * Hermetic stand-in for the local omi bridge.
 *
 * Speaks the same `ws://<host>/app` JSON protocol as the real bridge but serves
 * fixed canned data, so `verify-simulator.mjs` can assert the app's behaviour
 * without a running backend, credentials, or network.
 *
 * Implements RFC 6455 directly on `node:http` — no `ws` dependency, matching
 * the pure-Node PNG decoder in the verify script.
 *
 * Usage:
 *   node scripts/mock-bridge.mjs [--port 8765]
 *
 * Control plane (so tests can trigger server-initiated traffic):
 *   GET  /control/health  -> {"ok":true,"clients":N}
 *   POST /control/push    -> body is the banner text; broadcast as {"type":"push"}
 */
import { createHash } from 'node:crypto'
import { createServer } from 'node:http'

const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

const portArg = process.argv.indexOf('--port')
const PORT = Number(portArg > -1 ? process.argv[portArg + 1] : (process.env.BRIDGE_PORT ?? 8765))

// ------------------------------------------------------------------ fixtures

export const MEMORIES = [
  { content: 'Prefers dense text over icons on the glasses display.' },
  { content: 'Ships desktop changes behind a named test bundle first.' },
  { content: 'Runs the backend test suite before every commit.' },
  { content: 'Keeps agent instructions in AGENTS.md, not CLAUDE.md.' },
  { content: 'Reviews PRs in the morning, writes code in the afternoon.' },
]

export const ACTION_ITEMS = [
  { description: 'Send the G2 plugin build to the hardware team', completed: false },
  { description: 'Reply to the Even Realities SDK thread', completed: true },
  { description: 'Draft the bridge protocol doc', completed: false },
]

export const TODAY_TEXT = [
  'Three conversations, two of them about the glasses plugin.',
  '',
  'You agreed to send a build to the hardware team by Friday and to write up the bridge protocol before the review.',
  'The afternoon block stayed clear, so the display work landed ahead of schedule.',
].join('\n')

/** Long enough to paginate into more than one page at 380 chars per page. */
export const CHAT_CHUNKS = [
  'Finish the glasses plugin first. ',
  'The display layer is done and the bridge protocol is settled, ',
  'so the remaining work is the verification harness — ',
  'and that is what unblocks everyone else on the team. ',
  'After that, the two things competing for your attention are ',
  'the bridge protocol write-up you promised before the review ',
  'and the build the hardware team is waiting on. ',
  'The write-up is cheaper and it removes a question that keeps ',
  'coming back in review, so do it next. ',
  'Leave the backlog triage for tomorrow morning; ',
  'nothing in it is blocking another person today, ',
  'and it will read very differently once the plugin is shipped.',
]

export const CHAT_FULL = CHAT_CHUNKS.join('')

const DELTA_INTERVAL_MS = Number(process.env.BRIDGE_DELTA_MS ?? 90)

// -------------------------------------------------------------- ws framing

function acceptKey(key) {
  return createHash('sha1')
    .update(key + WS_GUID)
    .digest('base64')
}

/** Encode a server -> client text frame (never masked, per RFC 6455). */
function encodeText(text) {
  const payload = Buffer.from(text, 'utf8')
  const len = payload.length
  let header
  if (len < 126) {
    header = Buffer.from([0x81, len])
  } else if (len < 65536) {
    header = Buffer.alloc(4)
    header[0] = 0x81
    header[1] = 126
    header.writeUInt16BE(len, 2)
  } else {
    header = Buffer.alloc(10)
    header[0] = 0x81
    header[1] = 127
    header.writeBigUInt64BE(BigInt(len), 2)
  }
  return Buffer.concat([header, payload])
}

function encodeControl(opcode, payload = Buffer.alloc(0)) {
  return Buffer.concat([Buffer.from([0x80 | opcode, payload.length]), payload])
}

/**
 * Pull as many complete frames as `buf` holds.
 * Returns { frames, rest } where each frame is { fin, opcode, payload }.
 */
function decodeFrames(buf) {
  const frames = []
  let offset = 0

  while (offset + 2 <= buf.length) {
    const first = buf[offset]
    const second = buf[offset + 1]
    const fin = (first & 0x80) !== 0
    const opcode = first & 0x0f
    const masked = (second & 0x80) !== 0
    let len = second & 0x7f
    let cursor = offset + 2

    if (len === 126) {
      if (cursor + 2 > buf.length) break
      len = buf.readUInt16BE(cursor)
      cursor += 2
    } else if (len === 127) {
      if (cursor + 8 > buf.length) break
      const big = buf.readBigUInt64BE(cursor)
      if (big > 0x3fffffffn) throw new Error('frame too large')
      len = Number(big)
      cursor += 8
    }

    let mask = null
    if (masked) {
      if (cursor + 4 > buf.length) break
      mask = buf.subarray(cursor, cursor + 4)
      cursor += 4
    }

    if (cursor + len > buf.length) break
    const payload = Buffer.from(buf.subarray(cursor, cursor + len))
    if (mask) {
      for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3]
    }
    frames.push({ fin, opcode, payload })
    offset = cursor + len
  }

  return { frames, rest: buf.subarray(offset) }
}

// ------------------------------------------------------------------- server

const clients = new Set()

function send(socket, message) {
  if (socket.destroyed) return
  socket.write(encodeText(JSON.stringify(message)))
}

export function broadcastPush(text) {
  for (const socket of clients) send(socket, { type: 'push', text })
  return clients.size
}

function handleMessage(socket, raw) {
  let msg
  try {
    msg = JSON.parse(raw)
  } catch {
    console.log('[mock-bridge] ignoring non-JSON frame')
    return
  }
  console.log(`[mock-bridge] <- ${msg.type}`)

  switch (msg.type) {
    case 'chat': {
      // Stream the answer the way the real bridge does: deltas first, then one
      // authoritative `chat_done` carrying the whole text.
      let index = 0
      const tick = setInterval(() => {
        if (socket.destroyed) {
          clearInterval(tick)
          return
        }
        if (index < CHAT_CHUNKS.length) {
          send(socket, { type: 'chat_delta', text: CHAT_CHUNKS[index++] })
          return
        }
        clearInterval(tick)
        send(socket, { type: 'chat_done', text: CHAT_FULL })
        console.log(`[mock-bridge] -> chat_done (${CHAT_FULL.length} chars)`)
      }, DELTA_INTERVAL_MS)
      break
    }
    case 'memories': {
      const limit = Number.isFinite(msg.limit) ? msg.limit : MEMORIES.length
      send(socket, { type: 'memories', items: MEMORIES.slice(0, limit) })
      break
    }
    case 'action_items':
      send(socket, { type: 'action_items', items: ACTION_ITEMS })
      break
    case 'today':
      send(socket, { type: 'today', text: TODAY_TEXT })
      break
    default:
      console.log(`[mock-bridge] unknown request type: ${msg.type}`)
  }
}

const server = createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/control/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: true, clients: clients.size }))
    return
  }
  if (req.method === 'POST' && req.url === '/control/push') {
    let body = ''
    req.on('data', (chunk) => (body += chunk))
    req.on('end', () => {
      const delivered = broadcastPush(body || 'hello from omi')
      console.log(`[mock-bridge] -> push to ${delivered} client(s)`)
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, delivered }))
    })
    return
  }
  res.writeHead(404).end('not found')
})

server.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key']
  if (!key) {
    socket.destroy()
    return
  }
  const path = (req.url ?? '').split('?')[0]
  if (path !== '/app') {
    console.log(`[mock-bridge] rejecting upgrade for ${path}`)
    socket.write('HTTP/1.1 404 Not Found\r\n\r\n')
    socket.destroy()
    return
  }

  socket.write(
    [
      'HTTP/1.1 101 Switching Protocols',
      'Upgrade: websocket',
      'Connection: Upgrade',
      `Sec-WebSocket-Accept: ${acceptKey(key)}`,
      '\r\n',
    ].join('\r\n'),
  )
  socket.setNoDelay(true)
  clients.add(socket)
  console.log(`[mock-bridge] client connected (${clients.size} total)`)

  let buffer = Buffer.alloc(0)
  // Continuation frames are assembled here; browsers do not fragment small
  // JSON, but a compliant peer is allowed to.
  let fragmentOpcode = null
  let fragments = []

  socket.on('data', (chunk) => {
    buffer = Buffer.concat([buffer, chunk])
    let decoded
    try {
      decoded = decodeFrames(buffer)
    } catch (error) {
      console.error(`[mock-bridge] framing error: ${error.message}`)
      socket.destroy()
      return
    }
    buffer = decoded.rest

    for (const frame of decoded.frames) {
      if (frame.opcode === 0x8) {
        socket.write(encodeControl(0x8))
        socket.end()
        return
      }
      if (frame.opcode === 0x9) {
        socket.write(encodeControl(0xa, frame.payload))
        continue
      }
      if (frame.opcode === 0xa) continue

      if (frame.opcode === 0x0) {
        fragments.push(frame.payload)
      } else {
        fragmentOpcode = frame.opcode
        fragments = [frame.payload]
      }
      if (!frame.fin) continue

      const payload = Buffer.concat(fragments)
      fragments = []
      const opcode = fragmentOpcode
      fragmentOpcode = null
      if (opcode === 0x1) handleMessage(socket, payload.toString('utf8'))
    }
  })

  const drop = () => {
    if (clients.delete(socket)) console.log(`[mock-bridge] client gone (${clients.size} left)`)
  }
  socket.on('close', drop)
  socket.on('error', drop)
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[mock-bridge] listening on ws://127.0.0.1:${PORT}/app`)
})

// Shut down cleanly so the verify script's process-group kill is not the only
// thing standing between a failed run and a leaked port.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    for (const socket of clients) socket.destroy()
    server.close(() => process.exit(0))
  })
}
