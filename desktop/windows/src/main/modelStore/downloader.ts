import { createHash } from 'crypto'
import { createReadStream, createWriteStream } from 'fs'
import { mkdir, rename, rm, stat, copyFile, readFile } from 'fs/promises'
import { dirname } from 'path'
import type { ModelEntry, ModelDownloadProgress } from '../../shared/types'
import { hfDownloadUrl, modelDir, modelFilePath, modelPartPath } from './registry'
import { cacheCandidates, defaultCacheRoots, planResume, refPath } from './hfCache'

type Emit = (p: ModelDownloadProgress) => void

function exists(p: string): Promise<boolean> {
  return stat(p).then(
    () => true,
    () => false
  )
}
async function sizeOf(p: string): Promise<number> {
  try {
    return (await stat(p)).size
  } catch {
    return 0
  }
}

async function sha256OfFile(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const h = createHash('sha256')
    createReadStream(path)
      .on('error', reject)
      .on('data', (c) => h.update(c))
      .on('end', () => resolve(h.digest('hex')))
  })
}

/** If a complete/verified copy already exists in the HF cache, reuse it (no download). */
async function tryCache(entry: ModelEntry, target: string, emit: Emit): Promise<boolean> {
  const roots = defaultCacheRoots()
  for (const root of roots) {
    let commit: string | undefined
    try {
      commit = (await readFile(refPath(root, entry), 'utf8')).trim()
    } catch {
      /* no ref; may still hit a sha blob */
    }
    for (const cand of cacheCandidates(root, entry, commit)) {
      if (!(await exists(cand))) continue
      if (entry.sha256) {
        const got = await sha256OfFile(cand)
        if (got !== entry.sha256) continue
      }
      emit({ id: entry.id, received: 0, total: entry.sizeBytes, phase: 'cache' })
      await mkdir(dirname(target), { recursive: true })
      await copyFile(cand, target)
      emit({ id: entry.id, received: entry.sizeBytes, total: entry.sizeBytes, phase: 'done' })
      return true
    }
  }
  return false
}

/**
 * Download (or resume) one model into the app store.
 * - Reuses the HF cache when possible (team's "dedupe from cache" ask).
 * - Resumes via HTTP Range using the `.part` size.
 * - Verifies sha256 when known, else size; only then atomically renames.
 */
export async function downloadModel(
  entry: ModelEntry,
  userDataDir: string,
  emit: Emit,
  signal?: AbortSignal
): Promise<void> {
  const target = modelFilePath(userDataDir, entry)
  const part = modelPartPath(userDataDir, entry)
  await mkdir(modelDir(userDataDir, entry), { recursive: true })

  if (await exists(target)) {
    emit({ id: entry.id, received: entry.sizeBytes, total: entry.sizeBytes, phase: 'done' })
    return
  }
  if (await tryCache(entry, target, emit)) return

  const resume = planResume(await sizeOf(part), entry.sizeBytes)
  if (resume.complete) {
    // part already full -> treat as download done, then verify below
  } else {
    const headers: Record<string, string> = {}
    if (resume.rangeHeader) headers.Range = resume.rangeHeader
    let res: Response
    try {
      res = await fetch(hfDownloadUrl(entry), { headers, signal })
    } catch (e) {
      emit({ id: entry.id, received: resume.start, total: entry.sizeBytes, phase: 'error', error: (e as Error).message })
      return
    }
    if (!res.ok && res.status !== 206) {
      emit({ id: entry.id, received: resume.start, total: entry.sizeBytes, phase: 'error', error: `HTTP ${res.status}` })
      return
    }
    if (!res.body) {
      emit({ id: entry.id, received: resume.start, total: entry.sizeBytes, phase: 'error', error: 'no body' })
      return
    }
    const out = createWriteStream(part, { flags: resume.start > 0 ? 'a' : 'w' })
    let received = resume.start
    try {
      for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
        if (signal?.aborted) {
          out.destroy()
          emit({ id: entry.id, received, total: entry.sizeBytes, phase: 'cancelled' })
          return
        }
        const buf = Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength)
        received += buf.length
        emit({ id: entry.id, received, total: entry.sizeBytes, phase: 'download' })
        if (!out.write(buf)) await new Promise<void>((r) => out.once('drain', () => r()))
      }
      await new Promise<void>((resolve, reject) => {
        out.end()
        out.once('finish', () => resolve())
        out.once('error', reject)
      })
    } catch (e) {
      out.destroy()
      emit({ id: entry.id, received, total: entry.sizeBytes, phase: 'error', error: (e as Error).message })
      return
    }
  }

  // Verify, then promote .part -> final.
  emit({ id: entry.id, received: entry.sizeBytes, total: entry.sizeBytes, phase: 'verify' })
  const size = await sizeOf(part)
  if (entry.sha256) {
    const got = await sha256OfFile(part)
    if (got !== entry.sha256) {
      emit({ id: entry.id, received: size, total: entry.sizeBytes, phase: 'error', error: 'sha256 mismatch' })
      return
    }
  } else if (entry.sizeBytes && Math.abs(size - entry.sizeBytes) > entry.sizeBytes * 0.05) {
    emit({ id: entry.id, received: size, total: entry.sizeBytes, phase: 'error', error: `size ${size} != expected ~${entry.sizeBytes}` })
    return
  }
  await rename(part, target)
  emit({ id: entry.id, received: size, total: size, phase: 'done' })
}

export async function deleteModel(entry: ModelEntry, userDataDir: string): Promise<void> {
  await rm(modelDir(userDataDir, entry), { recursive: true, force: true })
}
