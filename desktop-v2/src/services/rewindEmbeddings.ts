/**
 * Rewind OCR embeddings — TS port of
 * `desktop/Desktop/Sources/Rewind/Services/OCREmbeddingService.swift`.
 *
 * Every screenshot with OCR text ≥ 20 chars gets an embedding of the form
 * `[AppName] WindowTitle\n<OCR text>` (so retrieval sees app context) using
 * `gemini-embedding-001` via the backend proxy. The 3072-dim vector is
 * L2-normalized by `embedText()` and stored in the screen-capture plugin's
 * SQLite as a little-endian f32 BLOB.
 *
 * Called from two places in `rewindStore.ts`:
 *   1. After each successful capture (fire-and-forget).
 *   2. Once on app mount via `backfillScreenshotEmbeddings()` to catch up.
 */

import { embedText, isEmbeddingUnavailable } from "@/services/embeddingService";
import {
  saveScreenshotEmbedding,
  screenshotsMissingEmbeddings,
} from "@/services/rewind";

/** Minimum OCR length to bother embedding (matches Swift's minTextLength). */
const MIN_OCR_CHARS = 20;

/** Delay between backfill embed calls to avoid hammering the proxy. */
const BACKFILL_DELAY_MS = 80;

/**
 * Format OCR text for embedding: prepend app + window context so queries
 * like "slack" or "figma" retrieve the right screenshots.
 * Mirrors `OCREmbeddingService.formatForEmbedding` in the Swift app.
 */
export function formatScreenshotForEmbedding(
  ocrText: string,
  appName: string,
  windowTitle: string,
): string {
  let header = `[${appName}]`;
  if (windowTitle) header += ` ${windowTitle}`;
  return `${header}\n${ocrText}`;
}

/**
 * Embed a single screenshot's OCR text and save the vector. Silently skips
 * rows with too little text. Safe to call fire-and-forget — errors are
 * logged but not propagated.
 */
export async function embedAndSaveScreenshot(
  dbId: number,
  ocrText: string,
  appName: string,
  windowTitle: string,
): Promise<void> {
  if (!ocrText || ocrText.length < MIN_OCR_CHARS) return;
  const formatted = formatScreenshotForEmbedding(ocrText, appName, windowTitle);
  try {
    const vec = await embedText(formatted, "RETRIEVAL_DOCUMENT");
    await saveScreenshotEmbedding(dbId, vec);
  } catch (err) {
    // Circuit open or transient failure — the backfill loop will retry later.
    // Don't spam the console on the per-capture hot path.
    if (!isEmbeddingUnavailable(err)) throw err;
  }
}

/**
 * Catch up on screenshots that were captured before this feature shipped
 * (or failed to embed at capture time). Runs serially with a small delay
 * so the backend proxy isn't overwhelmed on cold start.
 */
export async function backfillScreenshotEmbeddings(maxItems = 200): Promise<number> {
  const items = await screenshotsMissingEmbeddings(maxItems);
  if (items.length === 0) return 0;

  let done = 0;
  for (const it of items) {
    try {
      const formatted = formatScreenshotForEmbedding(it.ocr_text, it.app_name, it.window_title);
      const vec = await embedText(formatted, "RETRIEVAL_DOCUMENT");
      await saveScreenshotEmbedding(it.id, vec);
      done++;
      await new Promise((r) => setTimeout(r, BACKFILL_DELAY_MS));
    } catch (err) {
      if (isEmbeddingUnavailable(err)) {
        // Proxy is down — stop trying, the circuit breaker will reopen
        // later and the next backfill run will resume from here.
        console.warn("[Rewind] embedding proxy unavailable, stopping backfill");
        break;
      }
      console.warn("[Rewind] embed backfill failed for", it.id, err);
    }
  }
  if (done > 0) console.info(`[Rewind] embedded ${done} screenshot(s) via backfill`);
  return done;
}
