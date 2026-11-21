// Needs attention uses only the server ledger; tasks/events remain in their own destinations.
// Shared by the real Activity tab and hermetic render fixtures.
import { Button } from '@/components/ui/button';
import {
  canRetryAttention,
  notesFailureKind,
  type AttentionItem,
} from '@/lib/attentionItems';

export function AttentionItemsSection({
  items,
  retrying,
  errors,
  loadError = false,
  onRetry,
  onOpen,
}: {
  items: AttentionItem[];
  retrying: Set<string>;
  errors: Set<string>;
  loadError?: boolean;
  onRetry: (item: AttentionItem) => void;
  onOpen: (conversationId: string) => void;
}) {
  if (!items.length && !loadError) return null;
  return (
    <section className="mx-5 mt-4 max-h-80 overflow-y-auto" aria-label="Needs attention">
      <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-text-tertiary">
        Needs attention
      </h2>
      {loadError && (
        <p role="alert" className="mb-3 text-sm text-text-secondary">
          Attention items couldn’t load. Try again.
        </p>
      )}
      {items.map((item) => (
        <div
          key={item.id}
          className="mb-2 flex items-center justify-between gap-4 rounded-section border border-stroke bg-bg-secondary p-4"
        >
          <div className="min-w-0">
            <button
              className="border-0 bg-transparent p-0 text-left text-sm text-text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              onClick={() => onOpen(item.conversation_id)}
            >
              {item.title || 'Conversation needs attention'}
            </button>
            {item.kind === notesFailureKind && (
              <p className="mt-1 text-sm text-text-tertiary">
                Notes couldn’t be completed. Saved tasks and events are kept.
              </p>
            )}
            {errors.has(item.id) && (
              <p role="alert" className="mt-1 text-sm text-error">
                Couldn’t retry. Try again.
              </p>
            )}
          </div>
          {(canRetryAttention(item) || retrying.has(item.id)) && (
            <Button
              variant="secondary"
              size="sm"
              disabled={retrying.has(item.id)}
              onClick={() => onRetry(item)}
            >
              {retrying.has(item.id)
                ? 'Retrying…'
                : item.kind === notesFailureKind
                ? 'Re-run notes'
                : 'Retry'}
            </Button>
          )}
        </div>
      ))}
    </section>
  );
}
