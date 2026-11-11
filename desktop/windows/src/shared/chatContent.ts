// Published chat rendering contract for the Windows port. Sibling tracks (chat
// UI, agent timeline) code against these shapes. Types only — no rendering here.
//
// Mirrors macOS `Desktop/Sources/Providers/ChatProvider.swift` (ChatContentBlock,
// ToolCallStatus, ToolCallInput), `Chat/ChatResource.swift`,
// `Chat/ChatErrorState.swift`, and backend `backend/models/chat.py` (ChartData).

/** Lifecycle of a tool call. `slow`/`stalled` are still in-flight (promoted by
 *  the stall detector); only `completed`/`failed` are terminal. Mirrors macOS
 *  ChatProvider.swift `ToolCallStatus`. */
export type ToolCallStatus = 'running' | 'slow' | 'stalled' | 'completed' | 'failed'

/** Tool-call arguments for display. `summary` is the inline one-liner (path,
 *  command); `details` is the full JSON for the expanded view. Mirrors macOS
 *  ChatProvider.swift `ToolCallInput`. */
export interface ToolCallInput {
  summary: string
  details?: string
}

/**
 * A block of content within an AI message. Discriminated union on `type`,
 * mirroring macOS `ChatContentBlock` (ChatProvider.swift:165-191). Citations,
 * resources (ChatResource), chart data, error state, and typing are SIBLING
 * concerns rendered alongside blocks — they are NOT block kinds.
 *
 * Render-time pruning rule (for the future renderer PR, matching macOS):
 *  - `thinking` blocks are dropped once the stream for that turn completes.
 *  - `completed` tool-call groups are dropped after the turn settles, EXCEPT
 *    agent-related blocks (agentSpawn / agentCompletion), which persist.
 */
export type ChatContentBlock =
  // Markdown text, including GFM tables (the renderer handles tables inline).
  | { type: 'text'; id: string; text: string }
  // A tool invocation. `output` lives on the same block (no separate
  // tool_result block); status drives the inline spinner/label.
  | {
      type: 'toolCall'
      id: string
      name: string
      status: ToolCallStatus
      toolUseId?: string
      input?: ToolCallInput
      output?: string
    }
  // Model reasoning (pruned post-stream — see the rule above).
  | { type: 'thinking'; id: string; text: string }
  // Collapsible card with a summary + expandable full text (AI profile/discovery).
  | { type: 'discoveryCard'; id: string; title: string; summary: string; fullText: string }
  // A background agent was spawned from this turn (projects into a pill).
  | {
      type: 'agentSpawn'
      id: string
      pillId?: string
      sessionId: string
      runId: string
      title: string
      objective: string
    }
  // A background agent finished; carries its output + terminal status.
  | {
      type: 'agentCompletion'
      id: string
      pillId?: string
      sessionId?: string
      runId?: string
      title: string
      promptSnippet: string
      output: string
      status: string
    }

/** Where a chat resource card came from. Mirrors macOS `ChatResourceOrigin`. */
export type ChatResourceOrigin = 'userAttachment' | 'generatedArtifact'

/** Lifecycle state of a chat resource card. Mirrors macOS `ChatResource.State`
 *  (the `failed` case's associated message is carried out-of-band in the UI). */
export type ChatResourceState =
  | 'uploading'
  | 'ready'
  | 'failed'
  | 'retained'
  | 'opened'
  | 'dismissed'

/**
 * Resource / artifact card rendered in a sibling strip beside message blocks
 * (user attachments and agent-generated artifacts share this shape). Mirrors
 * macOS `Chat/ChatResource.swift`. Binary `imageData` from the Swift model is
 * intentionally omitted here — the wire/render contract carries only references
 * (`thumbnailUrl` / `uri`). Swift `thumbnailURL` is renamed `thumbnailUrl` here.
 */
export interface ChatResource {
  id: string
  origin: ChatResourceOrigin
  title: string
  subtitle?: string
  mimeType?: string
  thumbnailUrl?: string
  uri?: string
  artifactId?: string
  sessionId?: string
  runId?: string
  state: ChatResourceState
}

/** The single primary recovery CTA on a chat error card. Mirrors macOS
 *  `ChatErrorRecoveryAction`. */
export type ChatErrorRecovery = 'retry' | 'signIn' | 'installRuntime' | 'dismiss'

/**
 * The five recoverable, turn-level error states the chat surface renders inline
 * (NOT block kinds). Mirrors macOS `Chat/ChatErrorState.swift`. Errors outside
 * these five fall through to the generic error banner / dedicated sheets.
 */
export type ChatErrorState =
  | { kind: 'authRequired' }
  | { kind: 'timeout'; toolName?: string }
  | { kind: 'bridgeUnavailable'; reason: 'nodeMissing' | 'runtimeMissing' | 'crashed' | 'unknown' }
  | { kind: 'interrupted' }
  | { kind: 'noDataFound' }

/** One (label, value) point in a chart dataset. Mirrors backend
 *  `chat.py:ChartDataPoint`. */
export interface ChartDataPoint {
  label: string
  value: number
}

/** A named series of chart points. `color` is an optional hex string. Mirrors
 *  backend `chat.py:ChartDataset` (`data_points` → `dataPoints`). */
export interface ChartDataset {
  label: string
  dataPoints: ChartDataPoint[]
  color?: string
}

/**
 * Backend-supplied chart payload for a chat message. Windows-only renderer
 * (macOS has no chart UI) — type published here, no UI in this PR. Mirrors
 * backend `chat.py:ChartData` (`chart_type` → `chartType`, `x_label` → `xLabel`,
 * `y_label` → `yLabel`).
 */
export interface ChartData {
  chartType: 'line' | 'bar'
  title: string
  xLabel?: string
  yLabel?: string
  datasets: ChartDataset[]
}
