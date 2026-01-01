'use client';

import { User, Plus, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Person } from '@/types/user';

// Speaker avatar colors matching mobile app
const SPEAKER_COLORS = [
  'bg-amber-700/30 text-amber-300',    // brown
  'bg-blue-900/30 text-blue-300',       // navy
  'bg-emerald-800/30 text-emerald-300', // forest green
  'bg-rose-900/30 text-rose-300',       // burgundy
  'bg-cyan-700/30 text-cyan-300',       // teal
  'bg-lime-800/30 text-lime-300',       // olive
  'bg-purple-800/30 text-purple-300',   // plum
  'bg-orange-800/30 text-orange-300',   // bronze
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
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-full',
        'text-sm font-medium transition-all duration-150',
        'border',
        selected
          ? 'bg-purple-primary/20 border-purple-primary text-purple-primary'
          : 'bg-bg-tertiary border-bg-quaternary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
        className
      )}
    >
      <div
        className={cn(
          'w-5 h-5 rounded-full flex items-center justify-center text-xs',
          selected ? 'bg-purple-primary/30 text-purple-primary' : colorClass
        )}
      >
        {person.name.charAt(0).toUpperCase()}
      </div>
      <span>{person.name}</span>
      {selected && <Check className="w-3.5 h-3.5" />}
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
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-full',
        'text-sm font-medium transition-all duration-150',
        'border',
        selected
          ? 'bg-purple-primary/20 border-purple-primary text-purple-primary'
          : 'bg-bg-tertiary border-bg-quaternary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
        className
      )}
    >
      <div
        className={cn(
          'w-5 h-5 rounded-full flex items-center justify-center',
          selected ? 'bg-purple-primary/30' : 'bg-purple-primary/20'
        )}
      >
        <User className="w-3 h-3 text-purple-primary" />
      </div>
      <span>You</span>
      {selected && <Check className="w-3.5 h-3.5" />}
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
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-full',
        'text-sm font-medium transition-all duration-150',
        'border border-dashed',
        'bg-bg-tertiary border-bg-quaternary text-text-tertiary',
        'hover:bg-bg-quaternary hover:text-text-secondary hover:border-text-quaternary',
        className
      )}
    >
      <Plus className="w-4 h-4" />
      <span>Add Person</span>
    </button>
  );
}
