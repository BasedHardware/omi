#!/usr/bin/env node
/**
 * The MCP server that exposes Omi's agent-control tools to a model.
 *
 * Spawned as a subprocess by the ACP bridge (Claude Code), which is itself a
 * subprocess of Electron main — so this process cannot reach the kernel directly.
 * It speaks MCP JSON-RPC on stdin/stdout and relays every `tools/list` and
 * `tools/call` back to the host over the local socket named in OMI_BRIDGE_PIPE,
 * authenticating with OMI_BRIDGE_TOKEN. Windows port of macOS'
 * agent/src/omi-tools-stdio.ts.
 *
 * THIS PROCESS IS NOT A SECURITY BOUNDARY, AND MUST NOT BE TREATED AS ONE.
 * It runs alongside a model that can execute shell commands, so assume the model
 * can read this file, read its env, and speak to the socket directly. Every
 * decision that matters — which tools exist, who the caller is, what it may do —
 * is made host-side in controlMcpBridge.ts / controlTools.ts. Nothing here is
 * trusted, so there is deliberately no policy logic in this file: it does not
 * filter the tool list, does not know the owner, and cannot name one.
 *
 * SINGLE FILE ON PURPOSE. It is bundled via `import ... from './omi-mcp-entry.mjs?asset'`,
 * which emits exactly this file — a relative import of a sibling module would
 * resolve in dev and break in a packaged build. `createMcpServer` is exported so
 * the protocol can be unit-tested without spawning anything; `main()` runs only
 * when this file is the process entry point.
 */

import { createInterface } from 'node:readline'
import { createConnection } from 'node:net'
import { pathToFileURL } from 'node:url'

const PROTOCOL_VERSION = '2024-11-05'

/**
 * The MCP protocol core: JSON-RPC in, JSON-RPC out, tool work delegated to
 * `askHost`. Transport-free so it can be driven directly by a test.
 *
 * @param {{ askHost: (frame: object) => Promise<any>, send: (message: object) => void }} io
 */
export function createMcpServer({ askHost, send }) {
  const errorResponse = (id, code, message) => {
    send({ jsonrpc: '2.0', id, error: { code, message } })
  }

  /**
   * A tool DENIAL is a result, not a protocol error: the model should see why it
   * was refused (and adapt) rather than get a transport fault. The host already
   * returns a JSON envelope with `ok: false` for denials, so relay it verbatim.
   * Only a broken relay is an error response.
   */
  const toolResult = (id, text) => {
    send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text }] } })
  }

  async function handleMessage(body) {
    const id = body.id ?? null
    // A notification has no id and takes no response — not even an error.
    const isNotification = body.id === undefined || body.id === null
    const method = body.method

    if (typeof method !== 'string') {
      if (!isNotification) errorResponse(id, -32600, 'Invalid Request: method must be a string')
      return
    }

    const params =
      body.params && typeof body.params === 'object' && !Array.isArray(body.params)
        ? body.params
        : {}

    switch (method) {
      case 'initialize':
        if (!isNotification) {
          send({
            jsonrpc: '2.0',
            id,
            result: {
              protocolVersion: PROTOCOL_VERSION,
              capabilities: { tools: {} },
              serverInfo: { name: 'omi', version: '1.0.0' }
            }
          })
        }
        return

      case 'notifications/initialized':
        return

      case 'tools/list': {
        if (isNotification) return
        try {
          const frame = await askHost({ type: 'list' })
          send({ jsonrpc: '2.0', id, result: { tools: frame.tools ?? [] } })
        } catch (error) {
          errorResponse(id, -32603, `Failed to list Omi tools: ${error.message}`)
        }
        return
      }

      case 'tools/call': {
        if (isNotification) return
        const name = params.name
        if (typeof name !== 'string' || !name) {
          errorResponse(id, -32602, 'Invalid params: tools/call requires a tool name')
          return
        }
        const args =
          params.arguments &&
          typeof params.arguments === 'object' &&
          !Array.isArray(params.arguments)
            ? params.arguments
            : {}
        try {
          // The host decides whether this tool exists and whether this caller may
          // call it. An unadvertised name is deliberately NOT filtered here: it is
          // rejected at dispatch, which is the only place a rejection is a gate.
          const frame = await askHost({ type: 'call', name, input: args })
          toolResult(id, frame.result ?? '')
        } catch (error) {
          errorResponse(id, -32603, `Omi tool call failed: ${error.message}`)
        }
        return
      }

      default:
        if (!isNotification) errorResponse(id, -32601, `Method not found: ${method}`)
    }
  }

  return {
    /** Handle one line of stdin. Never throws — hostile input must not kill us. */
    async handleLine(line) {
      if (!line.trim()) return
      let message
      try {
        message = JSON.parse(line)
      } catch {
        // No id is recoverable from unparseable input, so this response is
        // id-less, per the JSON-RPC spec.
        errorResponse(null, -32700, 'Parse error')
        return
      }
      if (!message || typeof message !== 'object' || Array.isArray(message)) {
        errorResponse(null, -32600, 'Invalid Request')
        return
      }
      try {
        await handleMessage(message)
      } catch (error) {
        errorResponse(message.id ?? null, -32603, `Internal error: ${error.message}`)
      }
    }
  }
}

// --- Host connection ---------------------------------------------------------

function logErr(message) {
  process.stderr.write(`[omi-mcp] ${message}\n`)
}

/**
 * Connect to the host bridge and speak its line-delimited relay protocol.
 * Returns an `askHost` bound to the live socket.
 */
function connectToHost(pipePath, token) {
  const pending = new Map()
  let counter = 0
  let buffer = ''

  return new Promise((resolve, reject) => {
    const socket = createConnection(pipePath, () => {
      socket.write(`${JSON.stringify({ type: 'hello', token })}\n`)
    })
    socket.setEncoding('utf8')

    const askHost = (frame) => {
      const callId = `mcp-${++counter}`
      return new Promise((settle, fail) => {
        pending.set(callId, { settle, fail })
        socket.write(`${JSON.stringify({ ...frame, callId })}\n`)
      })
    }

    socket.on('data', (chunk) => {
      buffer += chunk
      let newline = buffer.indexOf('\n')
      while (newline >= 0) {
        const line = buffer.slice(0, newline)
        buffer = buffer.slice(newline + 1)
        if (line.trim()) {
          let frame
          try {
            frame = JSON.parse(line)
          } catch {
            logErr(`ignoring malformed host frame: ${line.slice(0, 200)}`)
            newline = buffer.indexOf('\n')
            continue
          }
          if (frame.type === 'hello_ok') {
            resolve(askHost)
          } else if (frame.callId && pending.has(frame.callId)) {
            const { settle, fail } = pending.get(frame.callId)
            pending.delete(frame.callId)
            if (frame.type === 'error') {
              fail(new Error(frame.message ?? 'host rejected the call'))
            } else {
              settle(frame)
            }
          }
        }
        newline = buffer.indexOf('\n')
      }
    })

    // The host is the only thing that can answer. If it goes away, fail every
    // in-flight call rather than leaving the model hanging forever.
    const abort = (error) => {
      for (const [callId, { fail }] of pending) {
        pending.delete(callId)
        fail(error)
      }
      reject(error)
    }
    socket.on('error', abort)
    socket.on('close', () => abort(new Error('host connection closed')))
  })
}

const CONNECT_ATTEMPTS = 20
const CONNECT_RETRY_MS = 100

/**
 * The ACP bridge can spawn us before the host's socket is listening, which shows
 * up as ENOENT. Retry briefly rather than dying — a dead MCP server means the
 * model silently loses every control tool.
 */
async function connectWithRetry(pipePath, token) {
  let lastError
  for (let attempt = 1; attempt <= CONNECT_ATTEMPTS; attempt++) {
    try {
      return await connectToHost(pipePath, token)
    } catch (error) {
      lastError = error
      if (attempt < CONNECT_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, CONNECT_RETRY_MS))
      }
    }
  }
  throw lastError
}

async function main() {
  const pipePath = process.env.OMI_BRIDGE_PIPE
  const token = process.env.OMI_BRIDGE_TOKEN
  if (!pipePath || !token) {
    throw new Error('OMI_BRIDGE_PIPE / OMI_BRIDGE_TOKEN are not set')
  }

  const askHost = await connectWithRetry(pipePath, token)
  const server = createMcpServer({
    askHost,
    // stdout is the MCP channel and must stay pure JSON-RPC; logs go to stderr.
    send: (message) => process.stdout.write(`${JSON.stringify(message)}\n`)
  })

  const rl = createInterface({ input: process.stdin, terminal: false })
  rl.on('line', (line) => {
    void server.handleLine(line)
  })
  rl.on('close', () => process.exit(0))

  logErr('omi agent-control MCP server ready')
}

// Only run when spawned as the entry point — importing this module (as the unit
// tests do, for `createMcpServer`) must not try to open a socket.
const isEntryPoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href
if (isEntryPoint) {
  main().catch((error) => {
    logErr(`fatal: ${error.message}`)
    process.exit(1)
  })
}
