import { app } from 'electron'
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'http'
import type { AddressInfo } from 'net'
import { getLocalAgentSettings, LOCAL_AGENT_DEFAULT_PORT } from './settings'
import { ensureLocalAgentToken } from './tokenStore'
import { addObservabilityBreadcrumb, captureMainException } from '../observability'
import {
  errorResponseBody,
  listLocalAgentTools,
  runLocalAgentTool,
  type LocalAgentRuntimeContext
} from './tools'

const LOCAL_AGENT_HOST = '127.0.0.1'
const LOCAL_AGENT_APP_ID = 'com.omiwindows.app'
const MAX_PORT_ATTEMPTS = 20

export type LocalAgentServerInfo = {
  host: typeof LOCAL_AGENT_HOST
  port: number
  localUrl: string
  toolEndpoint: string
}

type AppMetadata = {
  name: string
  version: string
  appId: string
}

type LocalAgentServerOptions = {
  preferredPort?: number
  token?: string
  appMetadata?: AppMetadata
  serverFactory?: typeof createServer
}

let runningServer: Server | null = null
let runningInfo: LocalAgentServerInfo | null = null

function json(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(payload)
  })
  res.end(payload)
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    req.on('error', reject)
  })
}

function parseToolRequest(body: string): { name: string; arguments: unknown } {
  let payload: unknown
  try {
    payload = JSON.parse(body)
  } catch {
    throw new Error('invalid_json_body')
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('invalid_json_body')
  }
  const record = payload as Record<string, unknown>
  if (typeof record.name !== 'string' || !record.name.trim()) {
    throw new Error('missing_tool_name')
  }
  return {
    name: record.name.trim(),
    arguments: record.arguments ?? {}
  }
}

function authorize(req: IncomingMessage, token: string): boolean {
  const auth = req.headers.authorization
  return auth === `Bearer ${token}`
}

function metadata(override?: AppMetadata): AppMetadata {
  return (
    override ?? {
      name: app.getName(),
      version: app.getVersion(),
      appId: LOCAL_AGENT_APP_ID
    }
  )
}

function currentInfo(port: number): LocalAgentServerInfo {
  const localUrl = `http://${LOCAL_AGENT_HOST}:${port}`
  return {
    host: LOCAL_AGENT_HOST,
    port,
    localUrl,
    toolEndpoint: `${localUrl}/v1/local/tool`
  }
}

function route(
  req: IncomingMessage,
  res: ServerResponse,
  info: LocalAgentServerInfo,
  token: string,
  appInfo: AppMetadata
): void {
  const method = req.method ?? 'GET'
  const url = new URL(req.url ?? '/', info.localUrl)

  if (method === 'GET' && url.pathname === '/health') {
    json(res, 200, {
      ok: true,
      app: {
        name: appInfo.name,
        version: appInfo.version,
        appId: appInfo.appId
      },
      localUrl: info.localUrl,
      toolEndpoint: info.toolEndpoint
    })
    return
  }

  if (url.pathname === '/v1/local/tools' || url.pathname === '/v1/local/tool') {
    if (!authorize(req, token)) {
      json(res, 401, { error: 'unauthorized' })
      return
    }

    if (method === 'GET' && url.pathname === '/v1/local/tools') {
      json(res, 200, {
        ok: true,
        tools: listLocalAgentTools(),
        toolEndpoint: info.toolEndpoint
      })
      return
    }

    if (method === 'POST' && url.pathname === '/v1/local/tool') {
      void readBody(req)
        .then(async (body) => {
          let request: { name: string; arguments: unknown }
          try {
            request = parseToolRequest(body)
          } catch (error) {
            const message = error instanceof Error ? error.message : 'invalid_json_body'
            json(res, 400, { ok: false, error: { code: message, message } })
            return
          }

          try {
            const context: LocalAgentRuntimeContext = {
              localUrl: info.localUrl,
              toolEndpoint: info.toolEndpoint,
              app: {
                name: appInfo.name,
                version: appInfo.version,
                appId: appInfo.appId
              }
            }
            json(res, 200, await runLocalAgentTool(request.name, request.arguments, context))
          } catch (error) {
            const { status, body } = errorResponseBody(error)
            json(res, status, body)
          }
        })
        .catch(() => {
          json(res, 400, {
            ok: false,
            error: { code: 'invalid_request_body', message: 'invalid_request_body' }
          })
        })
      return
    }
  }

  json(res, 404, { error: 'not_found' })
}

function listen(server: Server, port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const onError = (error: Error): void => {
      server.off('listening', onListening)
      reject(error)
    }
    const onListening = (): void => {
      server.off('error', onError)
      resolve()
    }
    server.once('error', onError)
    server.once('listening', onListening)
    server.listen(port, LOCAL_AGENT_HOST)
  })
}

function closeServer(server: Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) reject(error)
      else resolve()
    })
  })
}

export async function startLocalAgentServer(
  options: LocalAgentServerOptions = {}
): Promise<LocalAgentServerInfo> {
  if (runningInfo) return runningInfo

  const token = options.token ?? ensureLocalAgentToken()
  const appInfo = metadata(options.appMetadata)
  const preferredPort = options.preferredPort ?? LOCAL_AGENT_DEFAULT_PORT
  const serverFactory = options.serverFactory ?? createServer

  addObservabilityBreadcrumb(
    'local_agent.server_start_requested',
    { preferredPort },
    { category: 'local_agent' }
  )

  let lastError: unknown = null
  for (let offset = 0; offset < MAX_PORT_ATTEMPTS; offset += 1) {
    const port = preferredPort + offset
    const info = currentInfo(port)
    const server = serverFactory((req, res) => route(req, res, info, token, appInfo))

    try {
      await listen(server, port)
      const address = server.address() as AddressInfo | null
      if (address?.address !== LOCAL_AGENT_HOST) {
        await closeServer(server)
        throw new Error(`local agent server bound unexpected address: ${address?.address}`)
      }
      runningServer = server
      runningInfo = info
      addObservabilityBreadcrumb(
        'local_agent.server_started',
        { port: info.port },
        { category: 'local_agent' }
      )
      console.log(`[local-agent] listening on ${info.localUrl}`)
      return info
    } catch (e) {
      lastError = e
      await closeServer(server).catch(() => undefined)
    }
  }

  const error =
    lastError instanceof Error ? lastError : new Error('local agent server failed to start')
  captureMainException('local_agent.server_start_failed', error, {
    preferredPort,
    attempts: MAX_PORT_ATTEMPTS
  })
  throw error
}

export async function startLocalAgentServerIfEnabled(): Promise<LocalAgentServerInfo | null> {
  const settings = getLocalAgentSettings()
  if (!settings.enabled) return null
  return startLocalAgentServer({ preferredPort: settings.port })
}

export function getLocalAgentServerInfo(): LocalAgentServerInfo | null {
  return runningInfo
}

export async function stopLocalAgentServer(): Promise<void> {
  const server = runningServer
  const info = runningInfo
  runningServer = null
  runningInfo = null
  if (server) {
    await closeServer(server)
    addObservabilityBreadcrumb(
      'local_agent.server_stopped',
      { port: info?.port ?? null },
      { category: 'local_agent' }
    )
  }
}
