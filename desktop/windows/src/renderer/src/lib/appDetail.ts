// Types + pure helpers for the per-app detail page (Apps → app detail), which
// mirrors the public Omi app store layout: header, About, Preview, Capabilities,
// Integration (triggers + setup steps), and Reviews. Field names match the Omi
// backend App model (backend/models/app.py) so `GET /v1/apps/:id` maps directly.

export type AuthStep = { name?: string; url?: string }

export type ExternalIntegration = {
  // What fires the app's webhook. 'memory_creation' is the backend's legacy name
  // for what the UI now calls a conversation.
  triggers_on?: string | null
  setup_completed_url?: string | null
  setup_instructions_file_path?: string | null
  is_instructions_url?: boolean | null
  app_home_url?: string | null
  auth_steps?: AuthStep[] | null
}

export type AppReview = {
  uid?: string
  score?: number
  review?: string
  username?: string | null
  // Developer's reply to the review, if any.
  response?: string | null
  rated_at?: string
  responded_at?: string
}

export type AppDetailEntry = {
  id: string
  name?: string
  description?: string
  image?: string | null
  author?: string | null
  category?: string | null
  capabilities?: string[]
  rating_avg?: number | null
  rating_count?: number | null
  installs?: number | null
  is_paid?: boolean
  price?: number | null
  // Per-user enabled flag the backend sometimes sets on the catalog entry.
  enabled?: boolean
  // Curation flags for ranking (most-popular / featured rows).
  is_popular?: boolean | null
  official?: boolean | null
  // Prompts the app runs (excluded from the reduced list — only the single-app
  // endpoint returns them). memory_prompt is the "summary" prompt shown on store.
  memory_prompt?: string | null
  chat_prompt?: string | null
  // Store "Preview" screenshots: `thumbnails` are ids (always in the reduced
  // list); `thumbnail_urls` are full URLs (only the slow single-app endpoint
  // computes them). We build URLs from the ids so previews load with the page.
  thumbnails?: string[] | null
  thumbnail_urls?: string[] | null
  external_integration?: ExternalIntegration | null
  proactive_notification?: { scopes?: string[] } | null
  reviews?: AppReview[]
}

function formatToken(raw: string): string {
  return raw
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}

// Capability tag → store label (matches the Omi app store wording).
const CAPABILITY_LABELS: Record<string, string> = {
  chat: 'Chat',
  persona: 'Persona',
  memories: 'Memories',
  external_integration: 'External Integration',
  proactive_notification: 'Proactive Notification'
}

export function capabilityLabel(cap: string): string {
  return CAPABILITY_LABELS[cap] ?? formatToken(cap)
}

// external_integration.triggers_on → human label.
const TRIGGER_LABELS: Record<string, string> = {
  memory_creation: 'Conversation Creation',
  transcript_processed: 'Transcript Processed',
  audio_bytes: 'Realtime Audio Bytes'
}

export function triggerLabel(triggersOn: string | null | undefined): string | null {
  if (!triggersOn) return null
  return TRIGGER_LABELS[triggersOn] ?? formatToken(triggersOn)
}

// Compact install count, "44.9k installs" style. Returns '' for nullish/zero so
// the caller can omit the line entirely.
export function formatInstalls(n: number | null | undefined): string {
  if (!n || n < 0) return ''
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
    .format(n)
    .toLowerCase() // 44.9K → 44.9k
}

// Destination of the "Setup <App>" step: the explicit setup-completed URL, else
// the app home, else the first auth step's URL. Null when nothing is configured.
export function setupUrl(ext: ExternalIntegration | null | undefined): string | null {
  if (!ext) return null
  return ext.setup_completed_url || ext.app_home_url || ext.auth_steps?.find((s) => s.url)?.url || null
}

// Reviewer display name — the backend leaves username null for anonymous raters.
export function reviewerName(r: AppReview): string {
  return (r.username && r.username.trim()) || 'Anonymous'
}

// Reviews shown in the list are only those with text content (the backend's
// /reviews view), so the section count can differ from rating_count.
export function reviewsWithText(reviews: AppReview[] | undefined): AppReview[] {
  if (!Array.isArray(reviews)) return []
  return reviews.filter((r) => typeof r.review === 'string' && r.review.trim().length > 0)
}

// Whole-star count (0–5) to render filled for a review/app score.
export function filledStars(score: number | null | undefined): number {
  if (!score || score < 0) return 0
  return Math.max(0, Math.min(5, Math.round(score)))
}

// Public GCS bucket that serves app preview screenshots (the backend's
// BUCKET_APP_THUMBNAILS). The single-app endpoint builds the same URLs server
// side, but it's slow — building them here from the list's thumbnail ids makes
// Preview load with the page. Backend pattern: `{bucket}/{thumbnail_id}.jpg`.
const APP_THUMBNAILS_BUCKET = 'app_thumbnails'

export function thumbnailUrl(thumbnailId: string): string {
  return `https://storage.googleapis.com/${APP_THUMBNAILS_BUCKET}/${thumbnailId}.jpg`
}

// Preview image URLs for an app. Prefer authoritative `thumbnail_urls` when the
// single-app endpoint has supplied them; otherwise build them from the `thumbnails`
// ids carried by the fast list. Already-absolute urls are passed through as-is.
export function previewUrls(app: {
  thumbnail_urls?: string[] | null
  thumbnails?: string[] | null
}): string[] {
  const urls = (app.thumbnail_urls ?? []).filter(Boolean) as string[]
  if (urls.length > 0) return urls
  return (app.thumbnails ?? [])
    .filter(Boolean)
    .map((t) => (/^https?:\/\//.test(t) ? t : thumbnailUrl(t)))
}
