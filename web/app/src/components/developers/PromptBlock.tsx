'use client';

import { useState } from 'react';
import { Check, ChevronDown, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Clipboard write with a two-second "Copied" latch. */
export function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return [copied, copy];
}

export function CopyButton({
  text,
  label,
  copiedLabel = 'Copied!',
  variant = 'primary',
  disabled = false,
  className,
}: {
  text: string;
  label: string;
  copiedLabel?: string;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  className?: string;
}) {
  const [copied, copy] = useCopy();
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => copy(text)}
      className={cn(
        'flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors',
        disabled
          ? 'cursor-not-allowed bg-bg-tertiary text-text-quaternary'
          : copied
          ? 'bg-green-500/20 text-green-400'
          : variant === 'primary'
          ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
        className,
      )}
    >
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {copied ? copiedLabel : label}
    </button>
  );
}

/**
 * A prompt preview that stays a few lines tall until expanded, so three of
 * them fit on one screen while the whole text is one click away.
 */
export function PromptPreview({ prompt, label }: { prompt: string; label: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div>
      <div className="relative">
        <pre
          aria-label={label}
          data-testid="agent-prompt"
          className={cn(
            'overflow-hidden whitespace-pre-wrap break-words rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-4 font-mono text-xs leading-relaxed text-text-secondary',
            expanded ? 'max-h-none' : 'max-h-36',
          )}
        >
          {prompt}
        </pre>
        {!expanded && (
          <div className="pointer-events-none absolute inset-x-px bottom-px h-12 rounded-b-xl bg-gradient-to-t from-[#0d0d0d] to-transparent" />
        )}
      </div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="mt-2 flex items-center gap-1 text-xs text-text-tertiary transition-colors hover:text-text-primary"
      >
        <ChevronDown
          className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')}
        />
        {expanded ? 'Show less' : 'Show full prompt'}
      </button>
    </div>
  );
}
