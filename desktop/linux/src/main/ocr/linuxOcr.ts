// src/main/ocr/linuxOcr.ts
// Linux OCR fallback using Tesseract
import { execFile } from 'child_process'
import { promisify } from 'util'
import { existsSync } from 'fs'
import type { OcrResult } from '../../shared/types'

const execFileAsync = promisify(execFile)

const TESSERACT_TIMEOUT_MS = 10000

function findTesseract(): string | null {
  const candidates = [
    'tesseract',
    '/usr/bin/tesseract',
    '/usr/local/bin/tesseract',
    '/nix/var/nix/profiles/default/bin/tesseract'
  ]
  for (const p of candidates) {
    if (existsSync(p)) return p
  }
  return null
}

let tesseractPath: string | null = null

export async function linuxOcr(jpeg: Buffer): Promise<OcrResult> {
  if (tesseractPath === null) {
    tesseractPath = findTesseract()
    if (!tesseractPath) {
      return {
        ok: false,
        code: 'TESSERACT_NOT_FOUND',
        message: 'Tesseract OCR not found. Install with: nix-env -iA nixpkgs.tesseract'
      }
    }
  }

  try {
    // Write JPEG to a temp file, run tesseract, read result
    const tmpFile = `/tmp/omi-ocr-${Date.now()}.jpg`
    const { writeFile, unlink } = await import('fs/promises')
    await writeFile(tmpFile, jpeg)

    try {
      const { stdout } = await execFileAsync(
        tesseractPath,
        [tmpFile, 'stdout', '-l', 'eng', '--psm', '6'],
        { timeout: TESSERACT_TIMEOUT_MS }
      )
      const text = stdout.trim()
      return {
        ok: true,
        fullText: text || '',
        lines: []
      }
    } finally {
      await unlink(tmpFile).catch(() => {})
    }
  } catch (e) {
    return {
      ok: false,
      code: 'TESSERACT_ERROR',
      message: (e as Error).message
    }
  }
}

export function isLinuxOcrAvailable(): boolean {
  return findTesseract() !== null
}
