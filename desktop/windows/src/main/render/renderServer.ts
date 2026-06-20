// In-process static server for the built renderer, used in PACKAGED builds only.
//
// Why not loadFile()? Loading from file:// gives Firebase Auth an unauthorized
// origin (signInWithPopup throws auth/unauthorized-domain), and file:// origins
// don't persist localStorage reliably across the dev→prod boundary. Serving the
// same bundle over http://localhost — an origin Firebase authorizes by default —
// fixes sign-in AND, because the port is fixed, keeps the origin (and its
// localStorage: Firebase session + onboarding flag) stable across launches.
//
// In DEV the Vite dev server already provides http://localhost:5179, so this is
// a no-op there. All three renderer windows (main, overlay, insight toast) load
// through loadRenderer() so they share one origin and therefore one auth session.
import { createServer, Server } from 'http'
import { createReadStream, existsSync } from 'fs'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { BrowserWindow } from 'electron'
import { contentTypeFor, requestToRelPath } from './renderServerLogic'

// Fixed, dedicated port (NOT the dev server's 5179) so the production origin is
// stable. If it's somehow taken we fall back to an ephemeral port — any localhost
// port is Firebase-authorized, so sign-in still works; only cross-launch
// persistence depends on the port staying constant.
const PROD_PORT = 41730

let baseUrl: string | null = null

/** Absolute path to the built renderer dir (out/renderer, inside the asar). */
function rendererRoot(): string {
  return join(__dirname, '../renderer')
}

function usingDevServer(): boolean {
  return is.dev && !!process.env['ELECTRON_RENDERER_URL']
}

/** The base origin to load from, or null when the dev server should be used. */
export function getRenderBaseUrl(): string | null {
  return baseUrl
}

function listen(server: Server, port: number, host: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const onError = (err: NodeJS.ErrnoException): void => reject(err)
    server.once('error', onError)
    server.listen(port, host, () => {
      server.removeListener('error', onError)
      const addr = server.address()
      resolve(typeof addr === 'object' && addr ? addr.port : port)
    })
  })
}

/**
 * Start the static server (packaged builds only). No-ops in dev and is safe to
 * call more than once. Must complete before any renderer window is loaded.
 */
export async function startRenderServer(): Promise<void> {
  if (usingDevServer() || baseUrl) return

  const root = rendererRoot()
  const server = createServer((req, res) => {
    const rel = requestToRelPath(req.url || '/')
    let filePath = join(root, rel)
    if (!existsSync(filePath)) filePath = join(root, 'index.html')
    if (!existsSync(filePath)) {
      res.statusCode = 404
      res.end('Not found')
      return
    }
    res.setHeader('Content-Type', contentTypeFor(filePath))
    createReadStream(filePath)
      .on('error', () => {
        if (!res.headersSent) res.statusCode = 500
        res.end()
      })
      .pipe(res)
  })

  let port = PROD_PORT
  try {
    port = await listen(server, PROD_PORT, '127.0.0.1')
  } catch {
    // Fixed port taken — fall back to an ephemeral one (auth still works).
    port = await listen(server, 0, '127.0.0.1')
  }
  baseUrl = `http://localhost:${port}`
}

/**
 * Load the built renderer into a window at an optional hash route. Uses the Vite
 * dev server in dev, the localhost static server in production, and falls back to
 * file:// only if the server never started (UI still renders; popup auth won't).
 */
export function loadRenderer(win: BrowserWindow, hash?: string): void {
  const devUrl = process.env['ELECTRON_RENDERER_URL']
  if (is.dev && devUrl) {
    win.loadURL(hash ? `${devUrl}#/${hash}` : devUrl)
    return
  }
  if (baseUrl) {
    win.loadURL(hash ? `${baseUrl}/#/${hash}` : `${baseUrl}/`)
    return
  }
  win.loadFile(join(rendererRoot(), 'index.html'), hash ? { hash } : undefined)
}
