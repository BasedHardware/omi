import { Socket } from 'node:net'
import { afterEach } from 'vitest'

// Fail before DNS or connection establishment. Loopback fixture servers and
// local IPC are the only real transports used by this unit/integration suite.
const connect = Socket.prototype.connect
const blocked: string[] = []
Socket.prototype.connect = function (...args: Parameters<Socket['connect']>): Socket {
  const first: unknown = args[0]
  const options = Array.isArray(first) ? first[0] : first
  const fields =
    typeof options === 'object' && options !== null
      ? (options as { path?: string; host?: string; port?: number | string })
      : undefined
  const path =
    fields?.path ?? (typeof options === 'string' && !/^\d+$/.test(options) ? options : undefined)
  const host = fields?.host ?? (typeof args[1] === 'string' ? args[1] : 'localhost')
  const port = Number(fields?.port ?? options)
  if (!path && (!['127.0.0.1', '::1', 'localhost'].includes(host) || port === 9)) {
    blocked.push(host)
    throw new Error(`Hermetic test blocked an unstubbed connection to ${host}`)
  }
  return Reflect.apply(connect, this, args) as Socket
} as Socket['connect']

afterEach(() => {
  if (blocked.length) {
    const hosts = blocked.splice(0)
    throw new Error(`Unstubbed network requests in this test: ${hosts.join(', ')}`)
  }
})
