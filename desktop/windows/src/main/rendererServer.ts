// Serves the packaged renderer over http://localhost:<port> instead of file://.
//
// Firebase's signInWithPopup validates window.location.origin against the
// project's authorized domains; `localhost` is authorized (and is what dev mode
// uses via the vite server on 5179), but a file:// origin fails hard with
// auth/unauthorized-domain — so a packaged build that loadFile()s the renderer
// can never sign in. Serving the same files over a loopback HTTP server gives
// every window the authorized `localhost` origin in production too.
//
// Port 5179 is preferred to match the dev server (web auth/localStorage state is
// per-origin INCLUDING port, so keeping it stable preserves the saved session
// across launches). If it's taken — e.g. a dev instance is running — the next
// free port is used; sign-in still works on any localhost port, the session
// just starts fresh for that run.
import { createServer, type Server } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, sep } from 'node:path'

const PREFERRED_PORT = 5179
const PORT_ATTEMPTS = 10

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

  for (let i = 0; i < PORT_ATTEMPTS; i++) {
    const port = PREFERRED_PORT + i
    if (await listen(server, port)) {
      baseUrl = `http://localhost:${port}`
      if (port !== PREFERRED_PORT) {
        console.warn(
          `[renderer-server] port ${PREFERRED_PORT} busy — using ${port} (saved session may not carry over)`
        )
      }
      console.log(`[renderer-server] serving ${root} at ${baseUrl}`)
      return baseUrl
    }
  }
  throw new Error(
    `[renderer-server] no free port in ${PREFERRED_PORT}–${PREFERRED_PORT + PORT_ATTEMPTS - 1}`
  )
}
