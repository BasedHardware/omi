import { ipcMain } from 'electron'
import type {
  ChatMessage,
  ClaudeAcpChatRequest,
  ClaudeAcpChatResponse,
  ClaudeAcpStatus
} from '../../shared/types'
import { getClaudeAcpStatus, sendClaudeAcpChat } from '../claudeAcp/client'

const MAX_CLAUDE_MESSAGES = 100
const MAX_CLAUDE_MESSAGE_CHARS = 20_000

function normalizeMessage(value: unknown): ChatMessage {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Claude ACP message must be an object')
  }
  const record = value as Partial<ChatMessage>
  if (record.role !== 'user' && record.role !== 'assistant') {
    throw new Error('Claude ACP message role must be user or assistant')
  }
  if (typeof record.content !== 'string') {
    throw new Error('Claude ACP message content must be a string')
  }
  if (record.content.length > MAX_CLAUDE_MESSAGE_CHARS) {
    throw new Error(`Claude ACP message content exceeds ${MAX_CLAUDE_MESSAGE_CHARS} characters`)
  }
  return { role: record.role, content: record.content }
}

export function normalizeClaudeAcpRequest(value: unknown): ClaudeAcpChatRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('invalid Claude ACP chat request')
  }
  const record = value as Partial<ClaudeAcpChatRequest>
  if (!Array.isArray(record.messages)) {
    throw new Error('Claude ACP chat requires messages')
  }
  if (record.messages.length === 0) {
    throw new Error('Claude ACP chat requires at least one message')
  }
  if (record.messages.length > MAX_CLAUDE_MESSAGES) {
    throw new Error(`Claude ACP chat accepts at most ${MAX_CLAUDE_MESSAGES} messages`)
  }
  return { messages: record.messages.map(normalizeMessage) }
}

export function registerClaudeAcpHandlers(): void {
  ipcMain.handle('claudeAcp:status', async (): Promise<ClaudeAcpStatus> => {
    return getClaudeAcpStatus()
  })
  ipcMain.handle(
    'claudeAcp:chatSend',
    async (_event, rawRequest: unknown): Promise<ClaudeAcpChatResponse> => {
      return sendClaudeAcpChat(normalizeClaudeAcpRequest(rawRequest).messages)
    }
  )
}
