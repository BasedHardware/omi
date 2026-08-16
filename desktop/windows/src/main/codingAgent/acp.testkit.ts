// Shared helpers for the mocked-subprocess ACP tests. Mirrors the macOS agent
// test pattern: a fake ChildProcess built from an EventEmitter with
// PassThrough pipes, plus a line-based JSON-RPC scripting harness. Test files
// own the `vi.mock('child_process')` call; this module only provides the
// building blocks (a shared file must not register mocks itself — hoisting is
// per test file).

import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { vi } from 'vitest'

export type MockAcpProcess = EventEmitter & {
  stdin: PassThrough
  stdout: PassThrough
  stderr: PassThrough
  kill: ReturnType<typeof vi.fn>
  pid: number
}

export function createMockProcess(): MockAcpProcess {
  const proc = Object.assign(new EventEmitter(), {
    stdin: new PassThrough(),
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: vi.fn(() => {
      proc.emit('exit', 0)
      return true
    }),
    pid: 23456
  }) as MockAcpProcess
  return proc
}

export type JsonRpcMessage = {
  jsonrpc: '2.0'
  id?: number
  method?: string
  params?: Record<string, unknown>
  result?: unknown
  error?: { code: number; message: string }
}

/** Parse every JSON-RPC line the adapter writes and hand it to the script. */
export function scriptJsonRpc(
  proc: MockAcpProcess,
  handler: (message: JsonRpcMessage) => void
): JsonRpcMessage[] {
  const seen: JsonRpcMessage[] = []
  proc.stdin.on('data', (chunk: Buffer) => {
    for (const line of chunk.toString().split('\n')) {
      if (!line.trim()) continue
      const message = JSON.parse(line) as JsonRpcMessage
      seen.push(message)
      handler(message)
    }
  })
  return seen
}

export function respond(proc: MockAcpProcess, id: number, result: unknown): void {
  proc.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', id, result })}\n`)
}

export function notify(proc: MockAcpProcess, method: string, params: unknown): void {
  proc.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`)
}

/** Answer the standard handshake so request() can get past ensureInitialized. */
export function answerCommonHandshake(
  proc: MockAcpProcess,
  message: JsonRpcMessage,
  nativeSessionId = 'native-session-1'
): boolean {
  if (message.method === 'initialize' && message.id !== undefined) {
    respond(proc, message.id, { protocolVersion: 1 })
    return true
  }
  if (message.method === 'session/new' && message.id !== undefined) {
    respond(proc, message.id, { sessionId: nativeSessionId })
    return true
  }
  // openBinding pins the session's permission mode (session/set_mode) right
  // after session/new so tool access doesn't inherit the machine's global
  // ~/.claude default — acknowledge it so the binding handshake completes.
  if (message.method === 'session/set_mode' && message.id !== undefined) {
    respond(proc, message.id, {})
    return true
  }
  return false
}

/** Temporarily override process.platform (restore with the returned fn). */
export function stubPlatform(platform: NodeJS.Platform): () => void {
  const original = Object.getOwnPropertyDescriptor(process, 'platform')!
  Object.defineProperty(process, 'platform', { value: platform, configurable: true })
  return () => Object.defineProperty(process, 'platform', original)
}
