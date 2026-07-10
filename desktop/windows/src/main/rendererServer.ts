// Serves the packaged renderer over http://localhost:<port> instead of file://.
//
// Firebase's signInWithPopup validates window.location.origin against the
// project's authorized domains; `localhost` is authorized (and is what dev mode
// uses via the vite server on 5179), but a file:// origin fails hard with
// auth/unauthorized-domain — so a packaged build that loadFile()s the renderer
// can never sign in. Serving the same files over a loopback HTTP server gives
// every window the authorized `localhost` origin in production too.
//
// The port is derived deterministically from the userData path (see
// portDerivation.ts): web auth/localStorage state is per-origin INCLUDING the
// port, so a stable per-install port preserves the saved session across
// launches, and distinct OMI_SANDBOX instances get distinct ports instead of
// racing for one. If the derived port is held we retry with backoff (a dying
// previous instance releases it within ~2s thanks to the single-instance
// lock); only a foreign squatter forces a fallback port — surfaced to the user
// because it means a one-time re-login (deliberate tradeoff: better than
// refusing to launch).
import { app, Notification } from 'electron'
import { createServer, type Server } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, sep } from 'node:path'
import { derivePort, planPortSequence } from './portDerivation'

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.map': 'application/json',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8'
}

let baseUrl: string | null = null

/** http://localhost:<port> once startRendererServer has resolved, else null (dev mode). */
export function rendererBaseUrl(): string | null {
  return baseUrl
}

function listen(server: Server, port: number): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const onError = (err: NodeJS.ErrnoException): void => {
      server.removeListener('listening', onListening)
      if (err.code === 'EADDRINUSE') resolve(false)
      else reject(err)
    }
    const onListening = (): void => {
      server.removeListener('error', onError)
      resolve(true)
    }
    server.once('error', onError)
    server.once('listening', onListening)
    server.listen(port, '127.0.0.1')
  })
}

/**
 * Start serving the built renderer directory (works transparently from inside
 * app.asar — Electron's patched fs handles it) and remember the resulting base
 * URL. Call once at startup in production, before any window loads.
 */
export async function startRendererServer(rendererRoot: string): Promise<string> {
  const root = normalize(rendererRoot)

  const server = createServer((req, res) => {
    void (async () => {
      const pathname = decodeURIComponent(new URL(req.url ?? '/', 'http://localhost').pathname)
      const rel = pathname === '/' ? 'index.html' : pathname.slice(1)
      const file = normalize(join(root, rel))
      // Containment check — never serve anything outside the renderer dir.
      if (file !== root && !file.startsWith(root + sep)) {
        res.writeHead(403).end()
        return
      }
      try {
        const body = await readFile(file)
        res.writeHead(200, {
          'content-type': MIME[extname(file).toLowerCase()] ?? 'application/octet-stream',
          'cache-control': 'no-cache'
        })
        res.end(body)
      } catch {
        res.writeHead(404).end()
      }
    })()
  })

  const derivedPort = derivePort(app.getPath('userData'))
  for (const attempt of planPortSequence(derivedPort)) {
    if (attempt.delayMs > 0) await sleep(attempt.delayMs)
    if (await listen(server, attempt.port)) {
      baseUrl = `http://localhost:${attempt.port}`
      if (attempt.isFallback) {
        console.warn(
          `[renderer-server] port ${derivedPort} held by another process — using ${attempt.port}; the saved session will not carry over (re-login needed)`
        )
        notifyFallbackPort()
      }
      console.log(`[renderer-server] serving ${root} at ${baseUrl}`)
      return baseUrl
    }
  }
  throw new Error(
    `[renderer-server] no free port near derived port ${derivedPort} — cannot serve the renderer`
  )
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** A fallback port means the origin changed and the saved sign-in is unreachable —
 * tell the user why they're being asked to log in again instead of failing silently. */
function notifyFallbackPort(): void {
  try {
    if (Notification.isSupported()) {
      new Notification({
        title: 'Omi started on a backup port',
        body: 'Another program was using Omi’s usual port, so you may need to sign in again.'
      }).show()
    }
  } catch {
    // Notification failures must never block startup.
  }
}
