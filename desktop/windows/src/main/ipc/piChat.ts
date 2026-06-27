import { app, ipcMain } from 'electron'
import type { PiChatRequest, PiChatResponse } from '../../shared/types'
import type { LocalAgentRuntimeContext } from '../localAgent/tools'
import { isPiChatEnabled, sendPiChat } from '../pi/chatBridge'

function runtimeContext(): LocalAgentRuntimeContext {
  return {
    localUrl: 'omi://local-agent',
    toolEndpoint: 'omi://local-agent/pi-chat-tool',
    app: {
      name: app.getName(),
      version: app.getVersion(),
      appId: 'com.omiwindows.app'
    }
  }
}

function normalizeRequest(value: unknown): PiChatRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('invalid Pi/Omi chat request')
  }
  const record = value as Partial<PiChatRequest>
  if (typeof record.token !== 'string') {
    throw new Error('Pi/Omi chat requires a Firebase ID token')
  }
  if (!Array.isArray(record.messages)) {
    throw new Error('Pi/Omi chat requires messages')
  }
  return {
    token: record.token,
    messages: record.messages
  }
}

export function registerPiChatHandlers(): void {
  ipcMain.handle('piChat:send', async (_event, rawRequest: unknown): Promise<PiChatResponse> => {
    if (!isPiChatEnabled()) {
      throw new Error('Pi/Omi chat is not enabled')
    }
    return sendPiChat(normalizeRequest(rawRequest), { runtimeContext: runtimeContext() })
  })
}
