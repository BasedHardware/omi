import { ipcMain } from 'electron'
import type {
  ClaudeAcpChatRequest,
  ClaudeAcpChatResponse,
  ClaudeAcpStatus
} from '../../shared/types'
import { getClaudeAcpStatus, sendClaudeAcpChat } from '../claudeAcp/client'

function normalizeRequest(value: unknown): ClaudeAcpChatRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('invalid Claude ACP chat request')
  }
  const record = value as Partial<ClaudeAcpChatRequest>
  if (!Array.isArray(record.messages)) {
    throw new Error('Claude ACP chat requires messages')
  }
  return { messages: record.messages }
}

export function registerClaudeAcpHandlers(): void {
  ipcMain.handle('claudeAcp:status', async (): Promise<ClaudeAcpStatus> => {
    return getClaudeAcpStatus()
  })
  ipcMain.handle(
    'claudeAcp:chatSend',
    async (_event, rawRequest: unknown): Promise<ClaudeAcpChatResponse> => {
      return sendClaudeAcpChat(normalizeRequest(rawRequest).messages)
    }
  )
}
