import { readFile, realpath, stat } from 'fs/promises'
import { extname, resolve, sep } from 'path'

export const MAX_REWIND_FRAME_BYTES = 8 * 1024 * 1024

export function isRewindFramePath(root: string, imagePath: string): boolean {
  const resolvedRoot = resolve(root)
  const resolvedPath = resolve(imagePath)
  return (
    extname(resolvedPath).toLowerCase() === '.jpg' &&
    (resolvedPath === resolvedRoot || resolvedPath.startsWith(resolvedRoot + sep))
  )
}

export function isRewindFrameSizeAllowed(bytes: number): boolean {
  return bytes <= MAX_REWIND_FRAME_BYTES
}

export async function readRewindFrame(root: string, imagePath: string): Promise<Buffer> {
  if (!isRewindFramePath(root, imagePath)) throw new Error('invalid frame path')
  const [canonicalRoot, canonicalPath] = await Promise.all([realpath(root), realpath(imagePath)])
  if (!isRewindFramePath(canonicalRoot, canonicalPath)) throw new Error('invalid frame path')
  const metadata = await stat(canonicalPath)
  if (!metadata.isFile()) throw new Error('invalid frame path')
  if (!isRewindFrameSizeAllowed(metadata.size)) throw new Error('frame exceeds preview size limit')
  return readFile(canonicalPath)
}
