// Pure helpers for the in-process renderer static server, split out so they can
// be unit-tested under node Vitest (the http/electron glue in renderServer.ts
// can't). Mirrors the foregroundTargetLogic split.
import { extname } from 'path'

const MIME: Record<string, string> = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.map': 'application/json',
  '.wasm': 'application/wasm',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav'
}

/** Content-Type for a file path, defaulting to a safe binary type. */
export function contentTypeFor(filePath: string): string {
  return MIME[extname(filePath).toLowerCase()] ?? 'application/octet-stream'
}

/**
 * Map a request URL path to a SAFE relative path under the renderer root:
 * strips query + hash, percent-decodes, drops any `..`/`.` segments (no path
 * traversal out of the root), and maps `/` to `index.html`. Because the app
 * uses HashRouter, the server only ever sees `/` and real asset paths.
 */
export function requestToRelPath(urlPath: string): string {
  let p = (urlPath || '/').split('?')[0].split('#')[0]
  try {
    p = decodeURIComponent(p)
  } catch {
    /* malformed escape — fall through with the raw path */
  }
  const segments = p.split(/[/\\]+/).filter((s) => s && s !== '.' && s !== '..')
  return segments.length ? segments.join('/') : 'index.html'
}
