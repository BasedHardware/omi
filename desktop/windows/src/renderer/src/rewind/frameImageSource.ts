/**
 * Turning a frame row into something an `<img>` can show, whichever way its
 * pixels are stored.
 *
 * Exactly one of `imagePath` / `chunkPath` locates a frame. Callers should not
 * have to know which — before compaction every frame was a JPEG and every call
 * site said so, and the point of routing here is that they can go on not
 * knowing.
 *
 * The reader is held across calls on purpose. A chunk is inter-frame
 * compressed, so a scrub that reopened the decoder per frame would be quadratic
 * in the chunk's length; keeping it alive makes a forward step one decode. That
 * is the whole reason this is an object and not a function.
 */

import type { RewindFrame } from '../../../shared/types'
import { ChunkFrameReader } from './chunkDecoder'

/** Where a frame's pixels are. */
export type FrameLocator =
  | { kind: 'jpeg'; imagePath: string }
  | { kind: 'chunk'; chunkPath: string; chunkOffset: number }
  | { kind: 'missing' }

/**
 * Read a frame row's locator.
 *
 * A row carrying both is not a state the writer can produce (claiming a frame
 * clears `image_path` in the same statement that sets `chunk_path`), but a
 * corrupt or partially-migrated row could, so the chunk wins: it is the one the
 * compactor verified before deleting anything.
 */
export function locateFrame(
  frame: Pick<RewindFrame, 'imagePath' | 'chunkPath' | 'chunkOffset'>
): FrameLocator {
  const chunkPath = frame.chunkPath
  const chunkOffset = frame.chunkOffset
  if (typeof chunkPath === 'string' && chunkPath !== '' && typeof chunkOffset === 'number') {
    return { kind: 'chunk', chunkPath, chunkOffset }
  }
  if (typeof frame.imagePath === 'string' && frame.imagePath !== '') {
    return { kind: 'jpeg', imagePath: frame.imagePath }
  }
  return { kind: 'missing' }
}

/**
 * Serves frame images to a view.
 *
 * One per view that shows frames. Object URLs it creates are owned by the
 * caller, which must revoke them; `dispose` drops the decoder.
 */
export class FrameImageSource {
  private reader: ChunkFrameReader | null = null

  /**
   * A `src` for this frame, or null when the row locates nothing.
   *
   * JPEG-backed frames come back as the data URL main has always returned.
   * Chunk-backed frames are decoded here and come back as an object URL, which
   * the caller revokes when it swaps images.
   */
  async srcFor(
    frame: Pick<RewindFrame, 'imagePath' | 'chunkPath' | 'chunkOffset'>
  ): Promise<{ src: string; revoke: boolean } | null> {
    const locator = locateFrame(frame)
    if (locator.kind === 'missing') return null
    if (locator.kind === 'jpeg') {
      const dataUrl = await window.omi.rewindFrameImage(locator.imagePath)
      return { src: dataUrl, revoke: false }
    }
    if (!this.reader) this.reader = new ChunkFrameReader()
    const blob = await this.reader.readFrame(locator.chunkPath, locator.chunkOffset, (path) =>
      window.omi.rewindChunkBytes(path)
    )
    return { src: URL.createObjectURL(blob), revoke: true }
  }

  /** Drop the live decoder. The next chunk read reopens. */
  dispose(): void {
    this.reader?.retire()
    this.reader = null
  }
}
