'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/src/lib/utils';

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

export default function CopyButton({
  value,
  label = 'Copy',
  className,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }, [value]);

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Copied' : label}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-neutral-300 transition-colors hover:border-white/20 hover:text-white',
        className,
      )}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-[#b9f36b]" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {copied ? 'Copied' : label}
    </button>
  );
}
