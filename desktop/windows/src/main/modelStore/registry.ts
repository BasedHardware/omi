import { join } from 'path'
import type { ModelEntry } from '../../shared/types'

/**
 * A small, curated set of well-known GGUF chat models. ids/labels/files are the
 * stable parts; `sizeBytes` is an expected-size hint for progress + a disk
 * preflight; `sha256` is optional — when known it enables content-addressed
 * verify + an exact Hugging Face cache hit, when absent we still dedupe by the
 * snapshot path and fall back to size verification.
 *
 * These are deliberately conservative popular repos; extend the list without
 * touching the downloader.
 */
export const MODEL_REGISTRY: ModelEntry[] = [
  {
    id: 'qwen2.5-3b-instruct-q4km',
    label: 'Qwen2.5 3B Instruct (Q4_K_M) — small, snappy',
    repo: 'bartowski/Qwen2.5-3B-Instruct-GGUF',
    file: 'Qwen2.5-3B-Instruct-Q4_K_M.gguf',
    revision: 'main',
    sizeBytes: 2_000_000_000,
    minRamGb: 6,
    vision: false
  },
  {
    id: 'qwen2.5-7b-instruct-q4km',
    label: 'Qwen2.5 7B Instruct (Q4_K_M) — stronger',
    repo: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
    file: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    revision: 'main',
    sizeBytes: 4_700_000_000,
    minRamGb: 8,
    vision: false
  },
  {
    id: 'llama-3.2-3b-instruct-q4km',
    label: 'Llama 3.2 3B Instruct (Q4_K_M)',
    repo: 'bartowski/Llama-3.2-3B-Instruct-GGUF',
    file: 'Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    revision: 'main',
    sizeBytes: 2_100_000_000,
    minRamGb: 6,
    vision: false
  },
  {
    id: 'qwen2.5-vl-3b-instruct-q4km',
    label: 'Qwen2.5-VL 3B Instruct (Q4_K_M) — vision',
    repo: 'mmengr7l/Qwen2.5-VL-3B-Instruct-GGUF',
    file: 'Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf',
    revision: 'main',
    sizeBytes: 2_200_000_000,
    minRamGb: 8,
    vision: true
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
