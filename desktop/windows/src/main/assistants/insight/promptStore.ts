// The Insight analysis prompt with Mac's versioned reset-on-bump. File-backed
// (userData/insight-prompt.json) — a copy of focus/promptStore.ts, differing only
// in the file name and the default it falls back to.
//
// Each stored prompt carries the DEFAULT version it was based on; when
// CURRENT_PROMPT_VERSION moves past it, any user override is discarded so the user
// rejoins the current default. Mac's `migratePromptIfNeeded`, exactly.
import { app } from 'electron'
import { join } from 'path'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { CURRENT_PROMPT_VERSION, DEFAULT_ANALYSIS_PROMPT } from './prompt'

type Stored = {
  version: number
  customPrompt: string | null
}

function file(): string {
  return join(app.getPath('userData'), 'insight-prompt.json')
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
export function migrateInsightPromptIfNeeded(): void {
  const stored = read()
  if (stored.version >= CURRENT_PROMPT_VERSION) return
  write({ version: CURRENT_PROMPT_VERSION, customPrompt: null })
}

/** The analysis prompt (user's custom text, or the default). The DB schema block
 *  and any language directive are appended by prompt.buildSystemPrompt at call
 *  time, not stored here. */
export function getInsightAnalysisPrompt(): string {
  return read().customPrompt ?? DEFAULT_ANALYSIS_PROMPT
}

/** Test/teardown: drop the cache. */
export function _resetInsightPromptCache(): void {
  cache = null
}
