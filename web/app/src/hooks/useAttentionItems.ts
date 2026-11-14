// Account-scoped attention and acknowledged retries survive stale list reads.
// Unknown kinds can be opened but can never invoke a mutation.
import { useCallback, useEffect, useRef, useState } from 'react';
import { getAttentionItems, retryAttentionItem } from '@/lib/api';
import {
  canRetryAttention,
  isRetryNotRetryable,
  dedupeAttention,
  notesFailureKind,
  type AttentionItem,
} from '@/lib/attentionItems';

export function useAttentionItems(
  enabled: boolean,
  owner?: string,
  onResolved?: (id: string) => void,
) {
  const scope = `${enabled}:${owner ?? ''}`;
  const active = useRef(scope);
  const epoch = useRef(0);
  if (active.current !== scope) {
    active.current = scope;
    ++epoch.current;
  }
  const sequence = useRef(0);
  const busy = useRef(new Set<string>());
  const keys = useRef(new Map<string, string>());
  const accepted = useRef(new Map<string, { conversation: string; operation: string }>());
  const [state, setState] = useState({
    scope,
    items: [] as AttentionItem[],
    errors: new Set<string>(),
    loadError: false,
  });
  const [retrying, setRetrying] = useState(new Set<string>());
  useEffect(() => {
    const identity = scope;
    let current = true;
    busy.current.clear();
    keys.current.clear();
    accepted.current.clear();
    setRetrying(new Set());
    setState({ scope, items: [], errors: new Set(), loadError: false });
    async function refresh() {
      if (!enabled) return;
      const request = ++sequence.current;
      try {
        const page = await getAttentionItems();
        if (!current || active.current !== identity || request !== sequence.current)
          return;
        const items = page.enabled === false ? [] : page.items;
        for (const item of items) {
          for (const [id, ack] of accepted.current) {
            if (
              item.kind === notesFailureKind &&
              item.conversation_id === ack.conversation &&
              item.id !== id
            )
              accepted.current.delete(id);
          }
          if (
            item.retry.state === 'failed' &&
            item.retry.operation_id === accepted.current.get(item.id)?.operation
          )
            accepted.current.delete(item.id);
        }
        setState((previous) => ({ ...previous, items, loadError: false }));
      } catch {
        if (current && active.current === identity && request === sequence.current)
          setState((previous) => ({ ...previous, loadError: true }));
      }
    }
    void refresh();
    window.addEventListener('focus', refresh);
    return () => {
      current = false;
      ++sequence.current;
      window.removeEventListener('focus', refresh);
    };
  }, [scope, enabled]);
  const retry = useCallback(
    async (item: AttentionItem) => {
      if (
        !enabled ||
        !canRetryAttention(item) ||
        busy.current.has(item.id) ||
        [...accepted.current.values()].some(
          (ack) => ack.conversation === item.conversation_id,
        )
      )
        return;
      const identity = scope;
      const attemptEpoch = epoch.current;
      const isCurrent = () =>
        active.current === identity && epoch.current === attemptEpoch;
      ++sequence.current;
      busy.current.add(item.id);
      setRetrying(new Set(busy.current));
      setState((previous) => ({
        ...previous,
        errors: new Set([...previous.errors].filter((id) => id !== item.id)),
      }));
      const key = keys.current.get(item.id) ?? crypto.randomUUID();
      keys.current.set(item.id, key);
      try {
        const result = await retryAttentionItem(item.id, key);
        if (!isCurrent()) return;
        if (result.state === 'failed') keys.current.delete(item.id);
        if (!['in_progress', 'succeeded'].includes(result.state))
          throw new Error('Retry not accepted');
        keys.current.delete(item.id);
        onResolved?.(item.conversation_id);
        accepted.current.set(item.id, {
          conversation: item.conversation_id,
          operation: result.operation_id,
        });
        setState((previous) => ({
          ...previous,
          items: previous.items.filter((row) => row.id !== item.id),
        }));
      } catch (error) {
        if (isCurrent() && isRetryNotRetryable(error)) {
          keys.current.delete(item.id);
          onResolved?.(item.conversation_id);
        }
        if (isCurrent())
          setState((previous) => ({
            ...previous,
            errors: new Set([...previous.errors, item.id]),
          }));
      } finally {
        if (isCurrent()) {
          busy.current.delete(item.id);
          setRetrying(new Set(busy.current));
        }
      }
    },
    [enabled, scope, onResolved],
  );
  const items =
    enabled && state.scope === scope
      ? dedupeAttention(
          state.items.filter(
            (item) =>
              ![...accepted.current.values()].some(
                (ack) => ack.conversation === item.conversation_id,
              ),
          ),
        )
      : [];
  const conversationIds = new Set(
    enabled && state.scope === scope
      ? [
          ...items.map((item) => item.conversation_id),
          ...[...accepted.current.values()].map((item) => item.conversation),
        ]
      : [],
  );
  return {
    items,
    conversationIds,
    retry,
    retrying,
    errors: state.errors,
    loadError: enabled && state.scope === scope && state.loadError,
  };
}
