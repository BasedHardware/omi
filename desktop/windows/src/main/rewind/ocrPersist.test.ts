// M1 regression: OCR text is written from two places — the capture HOT path
// (captureService) and the slower backlog sweep (ocrService) — and only the sweep
// used to queue the text for embedding. Because the hot path marks the frame
// indexed=1, and the sweep only looks at indexed=0, the hot path's frames (the
// great majority) were OCR'd and then never embedded at all.
//
// The fix is structural: both writers now go through persistFrameOcr, which
// persists AND enqueues. These tests pin that fusion — if a future change
// persists without enqueueing, the feature silently stops indexing, and this
// fails.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OcrLine } from '../../shared/types'

const db = vi.hoisted(() => ({ setRewindFrameOcr: vi.fn() }))
const service = vi.hoisted(() => ({ enqueueRewindEmbedding: vi.fn() }))

vi.mock('../ipc/db', () => db)
vi.mock('./embeddingService', () => service)

import { persistFrameOcr } from './ocrPersist'

const LINES: OcrLine[] = [{ text: 'hello', x: 0, y: 0, w: 10, h: 5, confidence: 0.9 }]

beforeEach(() => vi.clearAllMocks())

describe('persistFrameOcr', () => {
  it('persists the text AND queues it for embedding — the two cannot drift apart', () => {
    persistFrameOcr(7, 'quarterly revenue projections', LINES)

    expect(db.setRewindFrameOcr).toHaveBeenCalledWith(
      7,
      'quarterly revenue projections',
      JSON.stringify(LINES)
    )
    expect(service.enqueueRewindEmbedding).toHaveBeenCalledWith(7, 'quarterly revenue projections')
  })

  it('still marks a frame indexed when OCR found nothing, but queues no embedding', () => {
    persistFrameOcr(8, '')

    // The frame must be marked indexed or the sweep would re-OCR it forever...
    expect(db.setRewindFrameOcr).toHaveBeenCalledWith(8, '', null)
    // ...but there is no content to embed.
    expect(service.enqueueRewindEmbedding).not.toHaveBeenCalled()
  })

  it('stores null (not "undefined") for boxes when there are none', () => {
    persistFrameOcr(9, 'some text here', null)
    expect(db.setRewindFrameOcr).toHaveBeenCalledWith(9, 'some text here', null)
  })
})
