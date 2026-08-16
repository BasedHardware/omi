// Presence checks for the config-write MCP connectors. A gated connector
// (Codex / OpenClaw / Hermes) must show a real "requires <tool>" state when its
// CLI or config is absent — never a dead button that shells out to a missing
// binary. These helpers answer "is this tool present on this machine?" without
// spawning anything: a PATH scan for the executable (+ Windows shim extensions)
// and plain existsSync checks. All are injectable (env / path args) for tests.

import { existsSync, statSync } from 'fs'
import { delimiter, join } from 'path'

/** Executable extensions Windows resolves on PATH (PATHEXT), plus the bare name. */
const WIN_EXExec = ['', '.cmd', '.exe', '.bat', '.ps1', '.com']

/**
 * True when `command` resolves to a file on `PATH`. Cross-platform: on win32 it
 * also probes the common shim extensions (a CLI is often `foo.cmd`). Never
 * spawns a process. `pathEnv` defaults to `process.env.PATH` (injectable).
 */
export function commandOnPath(command: string, pathEnv = process.env.PATH ?? ''): boolean {
  if (!command) return false
  const exts = process.platform === 'win32' ? WIN_EXExec : ['']
  for (const dir of pathEnv.split(delimiter)) {
    if (!dir) continue
    for (const ext of exts) {
      try {
        const candidate = join(dir, command + ext)
        if (existsSync(candidate) && statSync(candidate).isFile()) return true
      } catch {
        /* unreadable PATH entry — skip */
      }
    }
  }
  return false
}

/** True when a path exists and is a regular file. */
export function fileExists(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile()
  } catch {
    return false
  }
}

/** True when a path exists and is a directory. */
export function dirExists(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isDirectory()
  } catch {
    return false
  }
}
