// Read a captured frame's JPEG off disk, base64-encoded — what a vision model
// wants. Main reads `imagePath` directly; the `rewind:frameImage` IPC exists for
// the renderer (it returns a data: URL) and there is no reason for main to pay
// for that round-trip.
import { readFile } from 'fs/promises'
import type { RewindFrame } from '../../../shared/types'

/** null when the JPEG is missing — the retention sweep may have deleted it out
 *  from under a frame row we are still holding. */
export async function readFrameImageBase64(
  frame: Pick<RewindFrame, 'imagePath'>
): Promise<string | null> {
  try {
    const buf = await readFile(frame.imagePath)
    return buf.toString('base64')
  } catch {
    return null
  }
}
