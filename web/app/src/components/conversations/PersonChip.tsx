'use client';

import { User, Plus, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Person } from '@/types/user';

// Speaker avatar colors matching mobile app
const SPEAKER_COLORS = [
  'bg-amber-700/30 text-amber-300', // brown
  'bg-blue-900/30 text-blue-300', // navy
  'bg-emerald-800/30 text-emerald-300', // forest green
  'bg-rose-900/30 text-rose-300', // burgundy
  'bg-cyan-700/30 text-cyan-300', // teal
  'bg-lime-800/30 text-lime-300', // olive
  'bg-white/[0.14] text-text-secondary', // plum
  'bg-orange-800/30 text-orange-300', // bronze
];

interface PersonChipProps {
  person: Person;
  selected?: boolean;
  onClick?: () => void;
  colorIndex?: number;
  className?: string;
}

/**
 * Chip component for displaying and selecting a person
 */
export function PersonChip({
  person,
  selected = false,
  onClick,
  colorIndex = 0,
  className,
}: PersonChipProps) {
  const colorClass = SPEAKER_COLORS[colorIndex % SPEAKER_COLORS.length];

  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-3 py-1.5',
        'text-sm font-medium transition-all duration-150',
        'border',
        selected
          ? 'border-white/25 bg-white/[0.14] text-text-primary'
          : 'border-bg-quaternary bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
        className,
      )}
    >
      <div
        className={cn(
          'flex h-5 w-5 items-center justify-center rounded-full text-xs',
          selected ? 'bg-white/[0.14] text-text-primary' : colorClass,
        )}
      >
        {person.name.charAt(0).toUpperCase()}
      </div>
      <span>{person.name}</span>
      {selected && <Check className="h-3.5 w-3.5" />}
    </button>
  );
}

interface YouChipProps {
  selected?: boolean;
  onClick?: () => void;
  className?: string;
}

/**
 * Special chip for marking segments as "You" (the user)
 */
export function YouChip({ selected = false, onClick, className }: YouChipProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-3 py-1.5',
        'text-sm font-medium transition-all duration-150',
        'border',
        selected
          ? 'border-white/25 bg-white/[0.14] text-text-primary'
          : 'border-bg-quaternary bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
        className,
      )}
    >
      <div
        className={cn(
          'flex h-5 w-5 items-center justify-center rounded-full',
          selected ? 'bg-white/[0.14]' : 'bg-white/[0.14]',
        )}
      >
        <User className="h-3 w-3 text-text-primary" />
      </div>
      <span>You</span>
      {selected && <Check className="h-3.5 w-3.5" />}
    </button>
  );
}

interface AddPersonChipProps {
  onClick?: () => void;
  className?: string;
}

/**
 * Chip for adding a new person
 */
export function AddPersonChip({ onClick, className }: AddPersonChipProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-full px-3 py-1.5',
        'text-sm font-medium transition-all duration-150',
        'border border-dashed',
        'border-bg-quaternary bg-bg-tertiary text-text-tertiary',
        'hover:border-text-quaternary hover:bg-bg-quaternary hover:text-text-secondary',
        className,
      )}
    >
      <Plus className="h-4 w-4" />
      <span>Add Person</span>
    </button>
  );
}
