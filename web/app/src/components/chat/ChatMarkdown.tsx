'use client';

import { Streamdown } from 'streamdown';

interface ChatMarkdownProps {
  children: string;
  isStreaming?: boolean;
}

export function ChatMarkdown({ children, isStreaming = false }: ChatMarkdownProps) {
  return (
    <Streamdown
      mode={isStreaming ? 'streaming' : 'static'}
      isAnimating={isStreaming}
      parseIncompleteMarkdown={isStreaming}
      caret={isStreaming ? 'block' : undefined}
      className="prose prose-sm prose-invert max-w-none break-words text-text-primary prose-p:my-0 prose-p:leading-relaxed prose-headings:mb-2 prose-headings:mt-4 prose-headings:text-text-primary prose-headings:font-semibold prose-ul:my-2 prose-ol:my-2 prose-li:my-1 prose-strong:text-text-primary prose-a:text-text-secondary prose-a:underline prose-code:rounded prose-code:bg-bg-quaternary prose-code:px-1 prose-code:py-0.5 prose-code:text-text-primary prose-pre:my-3 prose-pre:bg-bg-primary prose-pre:text-text-secondary"
    >
      {children}
    </Streamdown>
  );
}
