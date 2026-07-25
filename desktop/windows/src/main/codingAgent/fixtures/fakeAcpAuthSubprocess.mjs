#!/usr/bin/env node
// Fake ACP peer that models Claude Code's real auth behavior for the
// fresh-machine sign-in test: `initialize` and `session/new` succeed WITHOUT
// credentials (auth is only enforced at prompt time, exactly like the real
// bridge), but `session/prompt` fails with the canonical -32000 auth-required
// error until a `<CLAUDE_CONFIG_DIR>/.credentials.json` with a claudeAiOauth
// access token exists. Once it does, the same prompt echoes normally.
//
// The credentials file is re-read on every prompt, so a restart (or just a
// later attempt) after sign-in picks up the new token. Console noise → stderr;
// stdout is pure JSON-RPC (ACP requirement).

/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JS fixture */
import { createInterface } from 'node:readline'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const rl = createInterface({ input: process.stdin, terminal: false })

function send(message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`)
}

function hasCredentials() {
  const dir = process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), '.claude')
  try {
    const parsed = JSON.parse(readFileSync(join(dir, '.credentials.json'), 'utf-8'))
    return typeof parsed?.claudeAiOauth?.accessToken === 'string' && parsed.claudeAiOauth.accessToken.length > 0
  } catch {
    return false
  }
}

rl.on('line', (line) => {
  if (!line.trim()) return
  let msg
  try {
    msg = JSON.parse(line)
  } catch {
    console.error(`[fake-acp-auth] unparseable line: ${line.slice(0, 120)}`)
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
      send({ id: msg.id, result: {} })
      break
    case 'session/prompt': {
      if (!hasCredentials()) {
        // The canonical ACP auth-required signal — the adapter must surface this
        // (as AcpError -32000), NOT swallow it as a generic -32601.
        send({ id: msg.id, error: { code: -32000, message: 'Authentication required' } })
        break
      }
      const text = (msg.params?.prompt ?? [])
        .filter((block) => block.type === 'text')
        .map((block) => block.text)
        .join(' ')
      send({
        method: 'session/update',
        params: {
          sessionId: 'fake-native-session',
          update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: `echo: ${text}` } }
        }
      })
      send({
        id: msg.id,
        result: {
          stopReason: 'end_turn',
          usage: { inputTokens: 1, outputTokens: 1, cachedReadTokens: 0, cachedWriteTokens: 0 }
        }
      })
      break
    }
    default:
      send({ id: msg.id, error: { code: -32601, message: `unhandled: ${msg.method}` } })
  }
})

process.stdin.on('end', () => process.exit(0))
