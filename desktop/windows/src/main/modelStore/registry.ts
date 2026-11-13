import { join } from 'path'
import type { ModelEntry } from '../../shared/types'

/**
 * A small, curated set of well-known GGUF chat models.
 *
 * SUPPLY-CHAIN PINNING POLICY: every entry is pinned to an explicit Hugging Face
 * commit `revision` (not `main`) and records the file's LFS `sha256`. Together
 * these mean: (1) the download URL is immutable, (2) the post-download verify is a
 * real content check (not just a ±5% size hint), and (3) the Hugging Face cache
 * dedupe is an exact `blobs/<sha256>` hit. An upstream re-quant therefore cannot
 * silently change the bytes users run. When adding an entry, resolve the current
 * commit + LFS oid from the HF API and paste them here — do not use `main`.
 *
 * sizes/oids verified against the HF API on 2026-09-22.
 */
export const MODEL_REGISTRY: ModelEntry[] = [
  {
    id: 'qwen2.5-3b-instruct-q4km',
    label: 'Qwen2.5 3B Instruct (Q4_K_M) — small, snappy',
    repo: 'bartowski/Qwen2.5-3B-Instruct-GGUF',
    file: 'Qwen2.5-3B-Instruct-Q4_K_M.gguf',
    revision: 'f302c64a2269a69fb27b2f9473b362f5bb8e78d8',
    sizeBytes: 1_929_903_264,
    sha256: '9c9f56a391a3abbd5b89d0245bf6106081bcc3173119d4229235dd9d23253f94',
    minRamGb: 6,
    vision: false
  },
  {
    id: 'qwen2.5-7b-instruct-q4km',
    label: 'Qwen2.5 7B Instruct (Q4_K_M) — stronger',
    repo: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
    file: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    revision: '8911e8a47f92bac19d6f5c64a2e2095bd2f7d031',
    sizeBytes: 4_683_074_240,
    sha256: '65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423',
    minRamGb: 8,
    vision: false
  },
  {
    id: 'llama-3.2-3b-instruct-q4km',
    label: 'Llama 3.2 3B Instruct (Q4_K_M)',
    repo: 'bartowski/Llama-3.2-3B-Instruct-GGUF',
    file: 'Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    revision: '5ab33fa94d1d04e903623ae72c95d1696f09f9e8',
    sizeBytes: 2_019_377_696,
    sha256: '6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff',
    minRamGb: 6,
    vision: false
  }
]

export function findModel(id: string): ModelEntry | undefined {
  return MODEL_REGISTRY.find((m) => m.id === id)
}

/** Where a model's file lives in the app's own store. Pure path math. */
export function modelDir(userDataDir: string, entry: ModelEntry): string {
  return join(userDataDir, 'models', entry.id)
}
export function modelFilePath(userDataDir: string, entry: ModelEntry): string {
  return join(modelDir(userDataDir, entry), entry.file)
}
export function modelPartPath(userDataDir: string, entry: ModelEntry): string {
  return modelFilePath(userDataDir, entry) + '.part'
}

/** The HF "resolve" download URL (optionally via a mirror host). */
export function hfDownloadUrl(entry: ModelEntry, endpoint = 'https://huggingface.co'): string {
  const base = endpoint.replace(/\/$/, '')
  return `${base}/${entry.repo}/resolve/${entry.revision}/${entry.file}`
}
