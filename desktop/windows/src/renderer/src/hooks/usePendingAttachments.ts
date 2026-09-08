import { useEffect, useState } from 'react'
import {
  getPendingAttachments,
  onPendingAttachments,
  type PendingAttachment
} from '../lib/chatAttachments'

// Subscribe to Track 1's module-level pending-attachments signal as React state.
// The signal replays its current value synchronously on subscribe, so the initial
// seed (getPendingAttachments) and the subscription can never miss or double an
// update — the subscription's first callback simply re-sets the same value.
export function usePendingAttachments(): PendingAttachment[] {
  const [list, setList] = useState<PendingAttachment[]>(getPendingAttachments)
  useEffect(() => onPendingAttachments(setList), [])
  return list
}
