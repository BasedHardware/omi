#!/usr/bin/env node
// Fake ACP peer for the real-subprocess integration test. Speaks just enough
// JSON-RPC 2.0 over stdio to exercise the adapter's real spawn/readline/kill
// machinery without any actual coding-agent install:
//   initialize     -> ack
//   session/new    -> mints a native session id
//   session/prompt -> streams one agent_message_chunk echoing the prompt text,
//                     then resolves with a stop reason + usage
// Console noise goes to stderr; stdout is pure JSON-RPC (ACP requirement).

/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JS fixture */
import { createInterface } from 'node:readline'

const rl = createInterface({ input: process.stdin, terminal: false })

function send(message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`)
}

rl.on('line', (line) => {
  if (!line.trim()) return
  let msg
  try {
    msg = JSON.parse(line)
  } catch {
    console.error(`[fake-acp] unparseable line: ${line.slice(0, 120)}`)
    return
  }
  if (msg.id === undefined || !msg.method) return // response or notification — ignore

  switch (msg.method) {
    case 'initialize':
      send({ id: msg.id, result: { protocolVersion: 1 } })
      break
    case 'session/new':
      send({ id: msg.id, result: { sessionId: 'fake-native-session' } })
      break
    case 'session/set_mode':
      // openBinding pins the session permission mode after session/new.
      send({ id: msg.id, result: {} })
      break
    case 'session/prompt': {
      const text = (msg.params?.prompt ?? [])
        .filter((block) => block.type === 'text')
        .map((block) => block.text)
        .join(' ')
      send({
        method: 'session/update',
        params: {
          sessionId: 'fake-native-session',
          update: {
            sessionUpdate: 'agent_message_chunk',
            content: { type: 'text', text: `echo: ${text}` }
          }
        }
      })
      // Cost arrives via the standard usage_update notification (cumulative
      // session cost), like @agentclientprotocol/claude-agent-acp emits it.
      send({
        method: 'session/update',
        params: {
          sessionId: 'fake-native-session',
          update: {
            sessionUpdate: 'usage_update',
            used: 7,
            size: 200000,
            cost: { amount: 0.002, currency: 'USD' }
          }
        }
      })
      send({
        id: msg.id,
        result: {
          stopReason: 'end_turn',
          usage: { inputTokens: 3, outputTokens: 4, cachedReadTokens: 0, cachedWriteTokens: 0 },
          _meta: { costUsd: 0.001 }
        }
      })
      break
    }
    default:
      send({ id: msg.id, error: { code: -32601, message: `unhandled: ${msg.method}` } })
  }
})

process.stdin.on('end', () => process.exit(0))
