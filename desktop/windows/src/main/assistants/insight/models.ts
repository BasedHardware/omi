// The Insight assistant's contract with Gemini: the Phase-1 and Phase-2 TOOL
// declarations (native function calling — Insight never uses a responseSchema,
// unlike Focus) and the pure parsers that turn a `functionCall`'s args into a
// persisted insight. Pure — no network, no Electron, no DB.
//
// The declarations are Mac's `buildPhase1Tools()` / `buildPhase2Tools()`
// (InsightAssistant.swift) translated 1:1, with ONE deliberate re-grounding: the
// table is Windows' `rewind_frames`, not Mac's `screenshots`, and the columns are
// the real Windows columns (`ts` epoch-ms not `timestamp` TEXT; `app`/
// `window_title`/`process_name`/`ocr_text`; no `focusStatus`). Every schema string
// the model sees must name a table/column that actually exists, or execute_sql
// resolves to nothing.
import type { InsightCategory } from '../../../shared/types'

/** One function call the model made, as decoded from a response part. */
export type ToolCall = {
  name: string
  args: Record<string, unknown>
  /** Opaque thinking signature — echoed back verbatim on the model turn so the
   *  thinking model keeps its chain across the tool round-trip. */
  thoughtSignature?: string
}

/** provide_advice's parsed args (Mac's `ExtractedInsight` + the two summary
 *  fields every terminal tool carries). `advice` is Mac's wire key for the
 *  insight text; `headline`/`reasoning` are optional. */
export type ExtractedInsight = {
  advice: string
  headline: string | null
  reasoning: string | null
  category: InsightCategory
  sourceApp: string
  confidence: number
  contextSummary: string
  currentActivity: string
}

/** The queryable rewind_frames schema, described exactly once and reused inside
 *  every tool description + the system-prompt schema block. */
export const REWIND_SCHEMA_DESC =
  'The rewind_frames table has: id INTEGER, ts INTEGER (epoch milliseconds), app TEXT, window_title TEXT, process_name TEXT, ocr_text TEXT.'

/** A single Gemini `tool` (one entry in the request's `tools` array). */
export type GeminiTool = { function_declarations: FunctionDeclaration[] }
type FunctionDeclaration = {
  name: string
  description: string
  parameters: {
    type: 'object'
    properties: Record<string, PropertySpec>
    required: string[]
  }
}
type PropertySpec = { type: string; description: string; enum?: string[] }

/** Phase 1 — text-only SQL investigation. execute_sql / request_screenshot /
 *  no_advice. (Mac buildPhase1Tools, re-grounded to rewind_frames.) */
export const PHASE1_TOOL: GeminiTool = {
  function_declarations: [
    {
      name: 'execute_sql',
      description: `Execute a SQL query on the local database to investigate screen activity. ${REWIND_SCHEMA_DESC} Use this to read OCR text from interesting windows, check what the user was doing, etc. SELECT queries only. Auto-limited to 200 rows.`,
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'SQL SELECT query to execute on the rewind_frames table'
          }
        },
        required: ['query']
      }
    },
    {
      name: 'request_screenshot',
      description:
        "Request to view a specific screenshot. Call this when you've found something interesting via SQL and want to see the actual screen. Provide the frame ID and a summary of your findings so far. The screenshot will be shown to you for final analysis.",
      parameters: {
        type: 'object',
        properties: {
          screenshot_id: {
            type: 'integer',
            description: 'The frame id from the rewind_frames table'
          },
          findings: {
            type: 'string',
            description:
              'Summary of what you found during investigation — what app, what OCR text caught your attention, and what you suspect might be worth advising about'
          }
        },
        required: ['screenshot_id', 'findings']
      }
    },
    {
      name: 'no_advice',
      description:
        'Call this when there is nothing worth advising about. Nothing qualifies as a specific, non-obvious insight. This ends the analysis.',
      parameters: {
        type: 'object',
        properties: {
          context_summary: {
            type: 'string',
            description: 'Brief summary of what user is looking at'
          },
          current_activity: {
            type: 'string',
            description: "High-level description of user's activity"
          }
        },
        required: ['context_summary', 'current_activity']
      }
    }
  ]
}

/** Phase 2 — single vision call + optional SQL cross-reference. execute_sql /
 *  provide_advice / no_advice. (Mac buildPhase2Tools, re-grounded.) */
export const PHASE2_TOOL: GeminiTool = {
  function_declarations: [
    {
      name: 'execute_sql',
      description: `Cross-reference your findings by querying the database. Use this to check if an issue was resolved in later screenshots, verify context across time, or look up related activity. ${REWIND_SCHEMA_DESC} SELECT queries only.`,
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'SQL SELECT query to execute on the rewind_frames table'
          }
        },
        required: ['query']
      }
    },
    {
      name: 'provide_advice',
      description:
        'Call this when you have a specific, non-obvious insight for the user based on the screenshot and your investigation findings. You should cross-reference first using execute_sql to verify the issue is still relevant.',
      parameters: {
        type: 'object',
        properties: {
          advice: {
            type: 'string',
            description:
              'The advice text (1-2 sentences, max 100 chars). Start with what you noticed, then why it matters.'
          },
          headline: {
            type: 'string',
            description:
              "Ultra-short observation (max 5 words) for notification preview. E.g. 'Draft saved in /tmp', 'Credentials visible in terminal'"
          },
          reasoning: {
            type: 'string',
            description: 'Brief explanation of why this advice is relevant'
          },
          category: {
            type: 'string',
            description: 'Category of insight',
            enum: ['productivity', 'communication', 'learning', 'other']
          },
          source_app: { type: 'string', description: 'App where context was observed' },
          confidence: {
            type: 'number',
            description:
              'Confidence score 0.0-1.0. 0.90+: preventing clear mistake. 0.75-0.89: highly relevant non-obvious tip. 0.60-0.74: useful but user might know.'
          },
          context_summary: {
            type: 'string',
            description: 'Brief summary of what user is looking at'
          },
          current_activity: {
            type: 'string',
            description: "High-level description of user's activity"
          }
        },
        required: [
          'advice',
          'headline',
          'category',
          'source_app',
          'confidence',
          'context_summary',
          'current_activity'
        ]
      }
    },
    {
      name: 'no_advice',
      description:
        "Call this when the screenshot doesn't reveal anything worth advising about, or when cross-referencing shows the issue was already resolved.",
      parameters: {
        type: 'object',
        properties: {
          context_summary: {
            type: 'string',
            description: 'Brief summary of what user is looking at'
          },
          current_activity: {
            type: 'string',
            description: "High-level description of user's activity"
          }
        },
        required: ['context_summary', 'current_activity']
      }
    }
  ]
}

// The tool enum only ever offers these four; `health` is Mac legacy kept only for
// decoding old records, never produced.
const VALID_CATEGORIES: readonly string[] = ['productivity', 'communication', 'learning', 'other']

function parseCategory(v: unknown): InsightCategory {
  return typeof v === 'string' && VALID_CATEGORIES.includes(v) ? (v as InsightCategory) : 'other'
}

/** A finite number, either as-is or parsed from a numeric string; null for
 *  anything else. The shared core of Mac's confidence and screenshot-id parses. */
function parseFiniteNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const n = Number(v.trim())
    if (Number.isFinite(n)) return n
  }
  return null
}

/** Mac's `confidence` extraction: number, then numeric string, else 0.5. */
function parseConfidence(v: unknown): number {
  return parseFiniteNumber(v) ?? 0.5
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

/** Mac's robust screenshot-id parse: integer, numeric string, or a float that is
 *  truncated. null when none of those hold (the model returned junk). */
export function parseScreenshotId(args: Record<string, unknown>): number | null {
  const n = parseFiniteNumber(args['screenshot_id'])
  return n == null ? null : Math.trunc(n)
}

/** provide_advice args → ExtractedInsight, with Mac's per-field fallbacks. */
export function parseProvideAdvice(args: Record<string, unknown>): ExtractedInsight {
  return {
    advice: str(args['advice']),
    headline: typeof args['headline'] === 'string' ? (args['headline'] as string) : null,
    reasoning: typeof args['reasoning'] === 'string' ? (args['reasoning'] as string) : null,
    category: parseCategory(args['category']),
    sourceApp: str(args['source_app']),
    confidence: parseConfidence(args['confidence']),
    contextSummary: str(args['context_summary']),
    currentActivity: str(args['current_activity'])
  }
}
