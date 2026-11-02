'use client';

import type { ReactElement } from 'react';
import { ChevronRight } from 'lucide-react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import type { MessageMemory } from '@/types/conversation';
import { normalizeChatCitations } from '@/lib/chatCitationLinks';

/**
 * Clickable source cards for the conversations an assistant reply cited.
 *
 * The backend resolves `[n]` markers on `done:` and persists the stripped prose
 * alongside ordered `memories` (`MessageConversation[]`), matching mobile's
 * `MemoriesMessageWidget` and macOS's `CitationCardsView`.
 */
export function ChatCitationCards({
  memories,
}: {
  memories?: readonly MessageMemory[] | null;
}): ReactElement | null {
  const router = useRouter();
  const citations = normalizeChatCitations(memories);
  if (citations.length === 0) return null;

  return (
    <section
      aria-label="Sources"
      data-testid="chat-citation-list"
      className="mt-2 flex flex-col gap-1.5"
    >
      {citations.map((citation) => (
        <a
          key={citation.id}
          href={citation.href}
          data-testid={`chat-citation-${citation.id}`}
          className="flex w-fit max-w-[85%] items-center gap-2 rounded-xl border border-stroke bg-bg-secondary/60 px-3.5 py-2 text-[13px] font-medium text-text-primary no-underline transition-colors hover:bg-bg-tertiary"
          onClick={(event) => {
            if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
              event.preventDefault();
              router.push(citation.href);
            }
          }}
        >
          <span aria-hidden="true" className="shrink-0 text-sm leading-none">
            {citation.emoji}
          </span>
          <span className="truncate">{citation.title}</span>
          <ChevronRight
            aria-hidden="true"
            className="ml-auto h-3.5 w-3.5 shrink-0 text-text-tertiary"
          />
        </a>
      ))}
    </section>
  );
}
