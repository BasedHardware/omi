import { spawn } from 'child_process'
import type { ChatMessage, ClaudeAcpChatResponse, ClaudeAcpStatus } from '../../shared/types'

const DEFAULT_COMMAND = 'claude'
const DEFAULT_ARGS = ['--print']
const REQUEST_TIMEOUT_MS = 120000

type SpawnResult = {
  ok: boolean
  stdout: string
  stderr: string
  exitCode: number | null
}

function command(): string {
  return (process.env.OMI_CLAUDE_ACP_COMMAND || DEFAULT_COMMAND).trim() || DEFAULT_COMMAND
}

function args(): string[] {
  const raw = process.env.OMI_CLAUDE_ACP_ARGS
  if (!raw?.trim()) return DEFAULT_ARGS
  return raw
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function promptFromMessages(messages: ChatMessage[]): string {
  const thread = messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => `${message.role === 'user' ? 'User' : 'Omi'}: ${message.content}`)
    .join('\n\n')
  if (!thread.trim()) throw new Error('Claude ACP requires at least one chat message')
  return [
    'You are Omi on Windows.',
    'Answer conversationally and use only the local Claude account/runtime available on this machine.',
    'Do not assume access to Omi-hosted Anthropic credentials.',
    '',
    thread
  ].join('\n')
}

function claudeEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env }
  for (const key of Object.keys(env)) {
    if (/ANTHROPIC.*API.*KEY|CLAUDE.*API.*KEY|OMI.*ANTHROPIC|VITE.*ANTHROPIC/i.test(key)) {
      delete env[key]
    }
  }
  return env
}

function runClaude(
  extraArgs: string[],
  input?: string,
  timeoutMs = REQUEST_TIMEOUT_MS
): Promise<SpawnResult> {
  return new Promise((resolve) => {
    const child = spawn(command(), extraArgs, {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
      env: claudeEnv()
    })
    let stdout = ''
    let stderr = ''
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      resolve({
        ok: false,
        stdout,
        stderr: stderr || 'Claude ACP request timed out',
        exitCode: null
      })
    }, timeoutMs)

    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf8')
    })
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf8')
    })
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ok: false, stdout, stderr: error.message, exitCode: null })
    })
    child.on('close', (exitCode) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ok: exitCode === 0, stdout, stderr, exitCode })
    })
    if (input) child.stdin.end(input)
    else child.stdin.end()
  })
}

function statusReason(result: SpawnResult): string | undefined {
  if (result.ok) return undefined
  const detail = (result.stderr || result.stdout).trim()
  if (/ENOENT|not found|not recognized/i.test(detail)) {
    return 'Claude command was not found'
  }
  if (/login|auth|oauth|account|credential/i.test(detail)) {
    return 'Claude account is not connected'
  }
  return detail || 'Claude ACP is unavailable'
}

export async function getClaudeAcpStatus(): Promise<ClaudeAcpStatus> {
  const result = await runClaude(['--version'], undefined, 10000)
  return {
    configured: result.ok,
    command: command(),
    authenticated: result.ok ? null : false,
    reason: statusReason(result)
  }
}

export async function sendClaudeAcpChat(messages: ChatMessage[]): Promise<ClaudeAcpChatResponse> {
  const prompt = promptFromMessages(messages)
  const result = await runClaude([...args(), prompt])
  if (!result.ok) {
    const reason = statusReason(result)
    throw new Error(reason ?? 'Claude ACP request failed')
  }
  const text = result.stdout.trim()
  if (!text) throw new Error('Claude ACP returned an empty response')
  return { text }
}
