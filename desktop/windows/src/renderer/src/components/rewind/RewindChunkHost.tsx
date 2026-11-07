import { useEffect } from 'react'
import type { RewindEncodeChunkRequest } from '../../../../shared/types'
import { encodeFramesToChunk } from '../../rewind/chunkEncoder'

/**
 * Answers the compactor's encode requests.
 *
 * Compaction is decided and executed in main, which has no `VideoEncoder`;
 * this is the renderer end of that. It holds no state and renders nothing —
 * every decision about what to encode, whether the result is trustworthy, and
 * what to delete afterwards is main's (see `main/rewind/chunks/`).
 *
 * Mounted next to `RewindCaptureHost`, so a window that can capture can also
 * compact. Any live window will do; main picks one.
 */
export function RewindChunkHost(): null {
  useEffect(() => {
    const encode = async (request: RewindEncodeChunkRequest): Promise<void> => {
      try {
        const bytes = await encodeFramesToChunk({
          width: request.width,
          height: request.height,
          frames: request.frames
        })
        window.omi.rewindChunkEncoded({
          requestId: request.requestId,
          ok: true,
          bytes: new Uint8Array(bytes)
        })
      } catch (e) {
        // Always answer. A silent failure here would leave the compactor
        // holding its plan and every loaded JPEG until the request times out.
        window.omi.rewindChunkEncoded({
          requestId: request.requestId,
          ok: false,
          error: e instanceof Error ? e.message : String(e)
        })
      }
    }
    return window.omi.onRewindEncodeChunk((request) => {
      void encode(request)
    })
  }, [])

  return null
}
