// The ledger owns notes eligibility; clients never infer it from Home noise.
// Widen the generated kind so future server kinds stay readable, without retry.
import type { AttentionItem as WireItem } from './omiApi.generated';

export type AttentionItem = Omit<
  WireItem,
  | 'kind'
  | 'title'
  | 'created_at'
  | 'duration_seconds'
  | 'failure_code'
  | 'seen'
  | 'started_at'
> & {
  kind: string;
  title?: string | null;
};
export const notesFailureKind = 'conversation_notes_failed_with_outputs';
export function canRetryAttention(item: AttentionItem): boolean {
  return (
    item.retryable &&
    [notesFailureKind, 'conversation_summary_failed'].includes(item.kind) &&
    ['none', 'failed'].includes(item.retry.state)
  );
}
export function dedupeAttention(items: AttentionItem[]): AttentionItem[] {
  const rows = new Map<string, AttentionItem>();
  for (const item of items) {
    const key = item.conversation_id || item.id;
    if (
      !rows.has(key) ||
      (item.kind === notesFailureKind && rows.get(key)?.kind !== notesFailureKind)
    )
      rows.set(key, item);
  }
  return [...rows.values()];
}

/** Only the endpoint's explicit terminal conflict acknowledges a stale retry. */
export function isRetryNotRetryable(error: unknown): boolean {
  return (
    error instanceof Error &&
    'status' in error &&
    error.status === 409 &&
    'state' in error &&
    error.state === 'not_retryable'
  );
}
