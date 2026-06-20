import { readFile } from 'fs/promises'
import { extname, resolve, sep } from 'path'
import type { RewindFrame, RewindFrameImageResult } from '../../shared/types'

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
  const root = resolve(rootPath)
  const full = resolve(imagePath)
  if (full !== root && !full.startsWith(root + sep)) return null
  return full
}

export async function readRewindFrameImage(
  frame: RewindFrame | null,
  rootPath: string
): Promise<RewindFrameImageResult> {
  if (!frame?.id) return frameImageNotFound('Frame not found')
  const full = resolveFrameImagePath(rootPath, frame.imagePath)
  if (!full) return frameImageNotFound('Frame image not found')
  try {
    const buf = await readFile(full)
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
