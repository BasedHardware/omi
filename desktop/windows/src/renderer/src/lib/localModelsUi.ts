import type { ModelEntry, ModelStatus } from '../../../shared/types'

/** Pure display/gating helpers for the Local models card (kept UI-free + testable). */

/** Human size: bytes -> "4.7 GB" / "812 MB" / "0 B". */
export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const gb = n / 1e9
  if (gb >= 1) return `${gb.toFixed(1)} GB`
  return `${Math.round(n / 1e6)} MB`
}

/** Download completion 0..100, clamped; total<=0 or unknown/NaN -> 0 (never NaN/div0). */
export function downloadPct(received: number, total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 0
  if (!Number.isFinite(received) || received <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((received / total) * 100)))
}

/**
 * Primary action label for a model row given its install state.
 * `partial` (a resumable half-file exists) still reads as "Resume".
 */
export function actionLabel(status: ModelStatus['state']): 'Download' | 'Resume' | 'Installed' {
  if (status === 'installed') return 'Installed'
  if (status === 'partial') return 'Resume'
  return 'Download'
}

/**
 * Advisory when we know the machine's RAM and it's under the model's floor.
 * `deviceRamGb` may be unknown (undefined) -> no warning (we don't guess).
 */
export function ramWarning(entry: ModelEntry, deviceRamGb?: number): string | undefined {
  if (typeof deviceRamGb !== 'number' || !Number.isFinite(deviceRamGb)) return undefined
  if (deviceRamGb >= entry.minRamGb) return undefined
  return `This model recommends ≥ ${entry.minRamGb} GB RAM; you have ~${Math.round(deviceRamGb)} GB. It may run slowly or fail to load.`
}

/** Sort/label helper: vision models flagged so the UI can note them. */
export function isVision(entry: ModelEntry): boolean {
  return entry.vision === true
}
