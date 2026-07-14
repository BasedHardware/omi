// The ONE place a frame's OCR text is persisted.
//
// This exists because of a real bug: OCR is written from two places — the capture
// hot path (captureService.refreshCurrentScreen) and the slower backlog sweep
// (ocrService) — and only the second one queued the text for semantic indexing.
// Since the hot path marks the frame `indexed = 1`, the backlog sweep (which
// selects `indexed = 0`) never revisited it, so the great majority of frames were
// OCR'd and then never embedded at all. The feature quietly indexed almost nothing.
//
// Persisting and enqueueing are therefore fused here and both callers go through
// this function. A future third OCR writer gets the embedding for free, and cannot
// reintroduce the same divergence by forgetting a call.
import { setRewindFrameOcr } from '../ipc/db'
import { enqueueRewindEmbedding } from './embeddingService'
import type { OcrLine } from '../../shared/types'

/**
 * Store a frame's OCR text (+ per-line boxes) and queue it for embedding.
 *
 * Enqueueing is fire-and-forget and never blocks: it only appends to an in-memory
 * queue that a background timer drains. `text` may be empty (OCR found nothing, or
 * the image was gone) — the frame is still marked indexed so nothing re-OCRs it,
 * and the embedder skips it.
 */
export function persistFrameOcr(frameId: number, text: string, lines?: OcrLine[] | null): void {
  setRewindFrameOcr(frameId, text, lines ? JSON.stringify(lines) : null)
  if (text) enqueueRewindEmbedding(frameId, text)
}
