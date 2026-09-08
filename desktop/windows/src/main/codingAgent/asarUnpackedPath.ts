// Redirect a bundled `?asset` path that resolves INSIDE `app.asar` to its
// asar-unpacked twin, so a plain-Node child (ELECTRON_RUN_AS_NODE) — and any
// native binary that child resolves relative to itself — reads and EXECUTES real
// files on disk instead of the archive.
//
// Why this is needed: the coding-agent ACP entry (claude-acp-entry.mjs) and the
// omi control MCP entry (omi-mcp-entry.mjs) are asar-UNPACKED in
// electron-builder.config.mjs, but the electron-vite `?asset` import still hands
// back a runtime path rooted at `__dirname` INSIDE `app.asar`
// (…/resources/app.asar/out/main/chunks/…). Electron's fs patch makes
// `existsSync()` return true for that archived path (it redirects the READ to the
// unpacked copy), which hides the problem — but the OS cannot EXEC a binary that
// lives inside the archive. The Claude Agent SDK resolves its `claude.exe`
// relative to the entry, lands on `app.asar/node_modules/.../claude.exe`, and its
// spawn fails; the ACP bridge surfaces that as a bare `-32603 "Internal error"`,
// which the agent pill shows as "Failed / Internal error". Dev builds have no
// asar, so the input is returned unchanged and behavior is identical.
//
// piMono.ts avoids the same trap by resolving `<resourcesPath>/app.asar.unpacked/…`
// directly instead of trusting `?asset`; this helper is the equivalent for the
// two `?asset`-imported entries.

import { existsSync } from 'fs'

/**
 * Map an absolute `?asset` entry path from its `app.asar` location to the
 * `app.asar.unpacked` twin when that twin exists on disk. Separator-agnostic
 * (electron-vite emits OS-native paths, but both `/` and `\\` are handled). Any
 * path without an `app.asar` segment — every dev path — is returned unchanged.
 *
 * `exists` is injectable purely for unit testing; it defaults to `fs.existsSync`.
 */
export function asarUnpackedEntryPath(
  assetPath: string,
  exists: (p: string) => boolean = existsSync
): string {
  // Match an `app.asar` PATH SEGMENT (bounded by separators on both sides), not a
  // substring, so an already-unpacked path ("app.asar.unpacked") is never rewritten.
  const unpacked = assetPath.replace(/([\\/])app\.asar([\\/])/, '$1app.asar.unpacked$2')
  if (unpacked === assetPath) return assetPath
  // Fall back to the original if the unpacked twin is somehow absent (a
  // misconfigured build) — never worse than today's behavior.
  return exists(unpacked) ? unpacked : assetPath
}
