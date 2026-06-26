import { app, ipcMain } from 'electron'
import type {
  PiChatAbortResponse,
  PiChatRequest,
  PiChatResponse,
  PiChatStartResponse,
  PiChatStreamEvent,
  PiChatStreamRequest
} from '../../shared/types'
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
    messages: record.messages,
    skillIds: Array.isArray(record.skillIds)
      ? record.skillIds.filter((id): id is string => typeof id === 'string')
      : undefined,
    modelId:
      typeof record.modelId === 'string' && record.modelId.trim()
        ? record.modelId.trim()
        : undefined
  }
}

function normalizeStreamRequest(value: unknown): PiChatStreamRequest {
  const request = normalizeRequest(value)
  const sessionId =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Partial<PiChatStreamRequest>).sessionId
      : undefined
  if (typeof sessionId !== 'string' || !sessionId.trim()) {
    throw new Error('Pi/Omi chat stream requires a session id')
  }
  return {
    ...request,
    sessionId: sessionId.trim()
  }
}

type ActivePiChatSession = {
  abort?: () => void
  aborted: boolean
  send: (event: PiChatStreamEvent) => void
}

const activeSessions = new Map<string, ActivePiChatSession>()

export function registerPiChatHandlers(): void {
  ipcMain.handle('piChat:send', async (_event, rawRequest: unknown): Promise<PiChatResponse> => {
    if (!isPiChatEnabled()) {
      throw new Error('Pi/Omi chat is not enabled')
    }
    return sendPiChat(normalizeRequest(rawRequest), { runtimeContext: runtimeContext() })
  })

  ipcMain.handle(
    'piChat:start',
    async (event, rawRequest: unknown): Promise<PiChatStartResponse> => {
      if (!isPiChatEnabled()) {
        throw new Error('Pi/Omi chat is not enabled')
      }

      const request = normalizeStreamRequest(rawRequest)
      if (activeSessions.has(request.sessionId)) {
        throw new Error('Pi/Omi chat session is already active')
      }

      const session: ActivePiChatSession = {
        aborted: false,
        send: (streamEvent) => {
          if (!event.sender.isDestroyed()) event.sender.send('piChat:event', streamEvent)
        }
      }
      activeSessions.set(request.sessionId, session)

      void sendPiChat(request, {
        runtimeContext: runtimeContext(),
        onController: (controller) => {
          session.abort = controller.abort
          if (session.aborted) controller.abort()
        },
        onStreamEvent: (streamEvent) => {
          session.send({ sessionId: request.sessionId, ...streamEvent })
        }
      })
        .catch((error) => {
          if (session.aborted) return
          session.send({
            sessionId: request.sessionId,
            type: 'error',
            message: error instanceof Error ? error.message : String(error)
          })
        })
        .finally(() => {
          activeSessions.delete(request.sessionId)
        })

      return { sessionId: request.sessionId }
    }
  )

  ipcMain.handle(
    'piChat:abort',
    async (_event, sessionId: string): Promise<PiChatAbortResponse> => {
      const session = activeSessions.get(sessionId)
      if (!session) return { aborted: false }
      session.aborted = true
      session.abort?.()
      session.send({ sessionId, type: 'aborted' })
      return { aborted: true }
    }
  )
}
