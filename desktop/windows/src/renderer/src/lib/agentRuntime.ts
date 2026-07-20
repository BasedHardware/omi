import { native, type AgentRuntimeEvent } from './native'

const clientId = crypto.randomUUID()
const workingDirectory = 'omi-desktop'
const sessionIds = new Map<string, string>()
const runtimeTimeoutMs = 15_000

type RuntimeRequest = Record<string, unknown> & { requestId: string }

function requestId(): string {
  return crypto.randomUUID()
}

function message(error: AgentRuntimeEvent): string {
  return error.failure?.userMessage ?? error.message ?? 'The Omi agent runtime failed.'
}

function withinRuntimeDeadline<T>(work: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error('Omi is taking too long to respond. Please try again.')),
      runtimeTimeoutMs
    )
    void work.then(
      (value) => {
        clearTimeout(timeout)
        resolve(value)
      },
      (error) => {
        clearTimeout(timeout)
        reject(error)
      }
    )
  })
}

async function request<T extends AgentRuntimeEvent>(payload: RuntimeRequest, expected: T['type']): Promise<T> {
  const event = await native.agentRuntimeRequest(payload)
  if (event.type === 'error') throw new Error(message(event))
  if (event.type !== expected) throw new Error('The Omi agent runtime returned an unexpected reply.')
  return event as T
}

async function resolveSession(ownerId: string, token: string, conversationId: string): Promise<string> {
  const key = `${ownerId}:${conversationId}`
  const existing = sessionIds.get(key)
  if (existing) return existing
  await native.agentRuntimeDispatch({ type: 'refresh_owner', ownerId })
  await native.agentRuntimeDispatch({ type: 'refresh_token', ownerId, token })
  await request(
    {
      type: 'configure_default_execution_profile',
      protocolVersion: 2,
      requestId: requestId(),
      clientId,
      ownerId,
      adapterId: 'rx4',
      modelProfile: 'omi-sonnet',
      workingDirectory
    },
    'default_execution_profile_configured'
  )
  const resolved = await request(
    {
      type: 'resolve_surface_session',
      protocolVersion: 2,
      requestId: requestId(),
      clientId,
      ownerId,
      surfaceKind: 'main_chat',
      externalRefKind: 'chat',
      externalRefId: conversationId
    },
    'surface_session_resolved'
  )
  const sessionId = resolved.sessionId
  if (!sessionId) throw new Error('The Omi agent runtime did not create a session.')
  sessionIds.set(key, sessionId)
  return sessionId
}

export async function streamAgentResponse(args: {
  ownerId: string
  token: string
  conversationId: string
  prompt: string
  onDelta: (text: string) => void
}): Promise<string> {
  const sessionId = await withinRuntimeDeadline(resolveSession(args.ownerId, args.token, args.conversationId))
  const id = requestId()
  return withinRuntimeDeadline((async () => {
    let unlisten: (() => void) | undefined
    let streamed = ''
    try {
      const response = new Promise<string>((resolve, reject) => {
        native.onAgentRuntimeEvent((event) => {
          if (event.requestId !== id) return
          if (event.type === 'text_delta' && event.text) {
            streamed += event.text
            args.onDelta(event.text)
            return
          }
          if (event.type === 'error') {
            reject(new Error(message(event)))
            return
          }
          if (event.type === 'result') {
            const text = streamed || event.text || ''
            if (!text.trim()) reject(new Error('The Omi agent runtime returned an empty reply.'))
            else resolve(text)
          }
        }).then((listener) => {
          unlisten = listener
          native.agentRuntimeDispatch({
            type: 'query',
            protocolVersion: 2,
            requestId: id,
            clientId,
            ownerId: args.ownerId,
            sessionId,
            prompt: args.prompt
          }).catch(reject)
        }, reject)
      })
      return await response
    } finally {
      unlisten?.()
    }
  })())
}
