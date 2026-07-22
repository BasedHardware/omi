// Shared toast for the "wrote N memories" tally that every memory-import surface
// (paste import, sticky-notes import, and their Settings equivalents) showed with
// byte-identical copy. One helper so the wording/tone rules live in one place.
import { toast } from './toast'
import type { BatchImportTally } from './memoriesBulk'

export function toastImportTally({ ok, failed, firstError }: BatchImportTally): void {
  toast(`Imported ${ok} memor${ok === 1 ? 'y' : 'ies'}${failed ? `, ${failed} failed` : ''}`, {
    tone: failed ? (ok ? 'warn' : 'error') : 'success',
    body: failed ? firstError : undefined
  })
}
