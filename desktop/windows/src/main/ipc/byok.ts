import { ipcMain } from 'electron'
import type {
  ByokChatRequest,
  ByokChatResponse,
  ByokChatProvider,
  ByokProvider,
  ByokSaveRequest,
  ByokStatus,
  ByokTestRequest,
  ByokUseRequest,
  ByokValidationResult,
  ChatMessage
} from '../../shared/types'
import { sendByokChat } from '../byok/chat'
import {
  deleteByokKey,
  getByokStatus,
  isByokChatProvider,
  isByokProvider,
  loadActiveByokChatKey,
  loadByokKey,
  recordByokValidation,
  saveByokKey,
  setActiveByokChatProvider
} from '../byok/store'
import { validateByokKey } from '../byok/validation'

function normalizeProvider(value: unknown): ByokProvider {
  if (!isByokProvider(value)) throw new Error('Unknown BYOK provider')
  return value
}

function normalizeChatProvider(value: unknown): ByokChatProvider {
  if (!isByokChatProvider(value)) throw new Error('This provider cannot be used for chat')
  return value
}

function normalizeKey(value: unknown): string {
  if (typeof value !== 'string') throw new Error('BYOK key is required')
  const key = value.trim()
  if (!key) throw new Error('BYOK key is required')
  return key
}

function normalizeMessages(value: unknown): ChatMessage[] {
  if (!Array.isArray(value)) throw new Error('BYOK chat requires messages')
  return value
    .filter((message): message is ChatMessage => {
      if (!message || typeof message !== 'object') return false
      const record = message as Partial<ChatMessage>
      return (
        (record.role === 'user' || record.role === 'assistant') &&
        typeof record.content === 'string'
      )
    })
    .map((message) => ({ id: message.id, role: message.role, content: message.content }))
}

function normalizeSaveRequest(raw: unknown): ByokSaveRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Invalid BYOK save request')
  }
  const record = raw as Partial<ByokSaveRequest>
  return {
    provider: normalizeProvider(record.provider),
    key: normalizeKey(record.key)
  }
}

function normalizeTestRequest(raw: unknown): ByokTestRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Invalid BYOK test request')
  }
  const record = raw as Partial<ByokTestRequest>
  return {
    provider: normalizeProvider(record.provider),
    key: typeof record.key === 'string' && record.key.trim() ? record.key.trim() : undefined
  }
}

function normalizeUseRequest(raw: unknown): ByokUseRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Invalid BYOK use request')
  }
  const record = raw as Partial<ByokUseRequest>
  return {
    provider: record.provider === null ? null : normalizeChatProvider(record.provider)
  }
}

function normalizeChatRequest(raw: unknown): ByokChatRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('Invalid BYOK chat request')
  }
  const record = raw as Partial<ByokChatRequest>
  return {
    messages: normalizeMessages(record.messages)
  }
}

export function registerByokHandlers(): void {
  ipcMain.handle('byok:status', async (): Promise<ByokStatus> => getByokStatus())

  ipcMain.handle('byok:save', async (_event, rawRequest: unknown): Promise<ByokStatus> => {
    const request = normalizeSaveRequest(rawRequest)
    return saveByokKey(request.provider, request.key)
  })

  ipcMain.handle('byok:delete', async (_event, rawProvider: unknown): Promise<ByokStatus> => {
    return deleteByokKey(normalizeProvider(rawProvider))
  })

  ipcMain.handle(
    'byok:test',
    async (_event, rawRequest: unknown): Promise<ByokValidationResult> => {
      const request = normalizeTestRequest(rawRequest)
      const key = request.key ?? loadByokKey(request.provider)
      if (!key) return { ok: false, error: 'No key saved for this provider' }
      const result = await validateByokKey(request.provider, key)
      if (!request.key) recordByokValidation(request.provider, result)
      return result
    }
  )

  ipcMain.handle('byok:use', async (_event, rawRequest: unknown): Promise<ByokStatus> => {
    const request = normalizeUseRequest(rawRequest)
    return setActiveByokChatProvider(request.provider)
  })

  ipcMain.handle(
    'byok:chatSend',
    async (_event, rawRequest: unknown): Promise<ByokChatResponse> => {
      const request = normalizeChatRequest(rawRequest)
      const active = loadActiveByokChatKey()
      if (!active) throw new Error('No BYOK chat provider is active')
      return sendByokChat(active.provider, active.key, request.messages)
    }
  )
}
