// The Focus system prompt with Mac's versioned reset-on-bump. File-backed
// (userData/focus-prompt.json), following the insight/state.ts pattern.
//
// Why the version dance at all: the prompt IS the product's definition of focus,
// and it is user-editable (a future Settings field). If we ship a better default
// but a user once saved a custom prompt, they would be frozen on the old wording
// forever. So each stored prompt carries the DEFAULT version it was based on;
// when CURRENT_PROMPT_VERSION moves past it, the custom prompt is discarded and
// the user rejoins the current default. Mac's `migratePromptIfNeeded`, exactly.
import { app } from 'electron'
import { join } from 'path'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { CURRENT_PROMPT_VERSION, DEFAULT_SYSTEM_PROMPT } from './prompt'

type Stored = {
  /** The DEFAULT version this file was last reconciled against. */
  version: number
  /** A user override, or null to use the current default. */
  customPrompt: string | null
}

function file(): string {
  return join(app.getPath('userData'), 'focus-prompt.json')
}

let cache: Stored | null = null

function read(): Stored {
  if (cache) return cache
  try {
    if (existsSync(file())) {
      const raw = JSON.parse(readFileSync(file(), 'utf8')) as Partial<Stored>
      cache = {
        version: typeof raw.version === 'number' ? raw.version : 0,
        customPrompt: typeof raw.customPrompt === 'string' ? raw.customPrompt : null
      }
      return cache
    }
  } catch {
    /* corrupt → treat as fresh */
  }
  cache = { version: 0, customPrompt: null }
  return cache
}

function write(next: Stored): void {
  cache = next
  try {
    writeFileSync(file(), JSON.stringify(next, null, 2))
  } catch {
    /* best-effort — a failed persist just re-runs the migration next launch */
  }
}

/** Run once at startup. If the stored version is behind, drop any custom prompt
 *  so the user picks up the new default, then stamp the current version. */
export function migrateFocusPromptIfNeeded(): void {
  const stored = read()
  if (stored.version >= CURRENT_PROMPT_VERSION) return
  write({ version: CURRENT_PROMPT_VERSION, customPrompt: null })
}

/** The system prompt to send Gemini: the user's custom text, or the default. */
export function getFocusSystemPrompt(): string {
  return read().customPrompt ?? DEFAULT_SYSTEM_PROMPT
}

/** Test/teardown: drop the cache. */
export function _resetFocusPromptCache(): void {
  cache = null
}
