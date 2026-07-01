import { realpathSync } from 'fs'
import { readFile, stat } from 'fs/promises'
import { extname, resolve, sep } from 'path'
import type { RewindFrame, RewindFrameImageResult } from '../../shared/types'

const MAX_FRAME_IMAGE_BYTES = 8 * 1024 * 1024

export function frameImageNotFound(message: string): RewindFrameImageResult {
  return { ok: false, code: 'not_found', message }
}

function imageMimeType(imagePath: string): string {
  const ext = extname(imagePath).toLowerCase()
  if (ext === '.png') return 'image/png'
  if (ext === '.webp') return 'image/webp'
  return 'image/jpeg'
}

function ocrPreview(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 240)
}

export function resolveFrameImagePath(rootPath: string, imagePath: string): string | null {
  try {
    const root = realpathSync(resolve(rootPath))
    const full = realpathSync(resolve(imagePath))
    const normalizedRoot = process.platform === 'win32' ? root.toLowerCase() : root
    const normalizedFull = process.platform === 'win32' ? full.toLowerCase() : full
    if (normalizedFull !== normalizedRoot && !normalizedFull.startsWith(normalizedRoot + sep)) {
      return null
    }
    return full
  } catch {
    return null
  }
}

async function readBoundedFrameImage(full: string): Promise<Buffer | null> {
  try {
    const info = await stat(full)
    if (!info.isFile() || info.size > MAX_FRAME_IMAGE_BYTES) return null
    return await readFile(full)
  } catch {
    return null
  }
}

export async function readRewindFrameImageDataUrl(
  imagePath: string,
  rootPath: string
): Promise<string | null> {
  const full = resolveFrameImagePath(rootPath, imagePath)
  if (!full) return null
  const buf = await readBoundedFrameImage(full)
  if (!buf) return null
  return `data:${imageMimeType(full)};base64,${buf.toString('base64')}`
}

export async function readRewindFrameImage(
  frame: RewindFrame | null,
  rootPath: string
): Promise<RewindFrameImageResult> {
  if (!frame?.id) return frameImageNotFound('Frame not found')
  const full = resolveFrameImagePath(rootPath, frame.imagePath)
  if (!full) return frameImageNotFound('Frame image not found')
  try {
    const buf = await readBoundedFrameImage(full)
    if (!buf) return frameImageNotFound('Frame image not found')
    return {
      ok: true,
      id: frame.id,
      ts: frame.ts,
      app: frame.app,
      windowTitle: frame.windowTitle,
      ocrPreview: ocrPreview(frame.ocrText),
      imageMimeType: imageMimeType(full),
      imageBase64: buf.toString('base64')
    }
  } catch {
    return frameImageNotFound('Frame image not found')
  }
}
