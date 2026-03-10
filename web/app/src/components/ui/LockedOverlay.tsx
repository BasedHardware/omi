'use client';

import { Lock } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LockedOverlayProps {
  label?: string;
  className?: string;
  onUpgrade?: () => void;
}

export function LockedOverlay({
  label = 'Upgrade to unlimited',
  className,
  onUpgrade,
}: LockedOverlayProps) {
  return (
    <div
      className={cn(
        'absolute inset-0 z-10 rounded-xl',
        'bg-black/10 backdrop-blur-[2px]',
        // Don’t block parent click handlers by default
        'pointer-events-none',
        className
      )}
      aria-hidden={!onUpgrade}
    >
      <div className="w-full h-full flex items-center justify-center">
        {onUpgrade ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onUpgrade();
            }}
            className={cn(
              'pointer-events-auto',
              'inline-flex items-center gap-2',
              'px-3 py-1.5 rounded-lg',
              'bg-black/40 hover:bg-black/55',
              'text-white text-sm font-semibold',
              'border border-white/15',
              'transition-colors'
            )}
            aria-label={label}
          >
            <Lock className="w-4 h-4" />
            {label}
          </button>
        ) : (
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/40 text-white text-sm font-semibold border border-white/15">
            <Lock className="w-4 h-4" />
            {label}
          </div>
        )}
      </div>
    </div>
  );
}
