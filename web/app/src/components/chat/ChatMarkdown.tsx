'use client';

import { useMemo } from 'react';
import { Streamdown, defaultRehypePlugins } from 'streamdown';
import { useRouter } from '@tschk/moonshine-next/navigation';
import type { MessageMemory } from '@/types/conversation';
import { chatCitationLinks } from '@/lib/chatCitationLinks';

interface ChatMarkdownProps {
  children: string;
  isStreaming?: boolean;
  memories?: MessageMemory[];
}

export function ChatMarkdown({
  children,
  isStreaming = false,
  memories = [],
}: ChatMarkdownProps) {
  const router = useRouter();
  const citationPlugin = useMemo(
    () => [chatCitationLinks, { memories }] as const,
    [memories],
  );
  return (
    <Streamdown
      key={JSON.stringify(memories.map((memory) => memory.id))}
      rehypePlugins={[...Object.values(defaultRehypePlugins), [...citationPlugin]]}
      components={{
        a: ({ node, children: label, ...props }) => {
          const index = Number(node?.properties?.dataChatCitation);
          if (!index || !memories[index - 1]?.id) return <a {...props}>{label}</a>;
          const destination = `/conversations?id=${encodeURIComponent(
            memories[index - 1].id,
          )}`;
          return (
            <a
              href={destination}
              aria-label={`Open source ${index}: ${memories[index - 1].structured.title}`}
              className="mx-0.5 inline-flex min-w-5 items-center justify-center rounded-full bg-bg-quaternary px-1.5 text-xs font-medium no-underline"
              onClick={(event) => {
                if (
                  !event.metaKey &&
                  !event.ctrlKey &&
                  !event.shiftKey &&
                  !event.altKey
                ) {
                  event.preventDefault();
                  router.push(destination);
                }
              }}
            >
              {label}
            </a>
          );
        },
      }}
      mode={isStreaming ? 'streaming' : 'static'}
      isAnimating={isStreaming}
      parseIncompleteMarkdown={isStreaming}
      caret={isStreaming ? 'block' : undefined}
      className="prose prose-sm prose-invert max-w-none break-words text-text-primary prose-headings:mb-2 prose-headings:mt-4 prose-headings:font-semibold prose-headings:text-text-primary prose-p:my-0 prose-p:leading-relaxed prose-a:text-text-secondary prose-a:underline prose-strong:text-text-primary prose-code:rounded prose-code:bg-bg-quaternary prose-code:px-1 prose-code:py-0.5 prose-code:text-text-primary prose-pre:my-3 prose-pre:bg-bg-primary prose-pre:text-text-secondary prose-ol:my-2 prose-ul:my-2 prose-li:my-1"
    >
      {children}
    </Streamdown>
  );
}
