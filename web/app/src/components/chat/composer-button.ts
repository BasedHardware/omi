import { cn } from '@/lib/utils';

// One alignment contract for every composer action control: fixed square box
// (40/36 px tiers), circular shape, flex-centered glyph, row containment.
// Structure only — no color or disabled-opacity token, so state classes can
// merge without tailwind-merge adjudication.
export const composerControlShell: string = cn(
  'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full sm:h-9 sm:w-9',
);

export const composerIconButton: string = cn(
  composerControlShell,
  'text-text-tertiary transition-colors hover:bg-white/[0.08] hover:text-text-primary',
  'disabled:cursor-not-allowed disabled:opacity-40',
);

export const composerSendButton: string = cn(
  composerControlShell,
  'bg-text-primary text-bg-primary transition-opacity hover:opacity-90',
  'disabled:cursor-not-allowed disabled:opacity-25',
);
