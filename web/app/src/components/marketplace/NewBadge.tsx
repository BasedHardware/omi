'use client';

import { type Plugin } from './types';

// Utility function to check if an app is new (within 7 days)
export function isNewApp(plugin: Plugin): boolean {
  // Return false immediately if created_at is null, undefined, or empty
  if (!plugin.created_at) {
    return false;
  }

  try {
    const creationDate = new Date(plugin.created_at);
    const now = new Date();

    // Validate the date - check for invalid dates and Unix epoch (which indicates null/invalid data)
    if (isNaN(creationDate.getTime()) || creationDate.getTime() === 0) {
      return false;
    }

    const diffInDays = Math.floor(
      (now.getTime() - creationDate.getTime()) / (1000 * 60 * 60 * 24),
    );

    return diffInDays <= 7;
  } catch (e) {
    return false;
  }
}

interface NewBadgeProps {
  plugin: Plugin;
  className?: string;
}

export function NewBadge({ plugin, className = '' }: NewBadgeProps) {
  if (!isNewApp(plugin)) return null;

  return (
    <span
      className={`inline-flex items-center rounded-full bg-[#6C8EEF]/15 px-2 py-0.5 text-xs font-medium text-[#6C8EEF] ${className}`}
    >
      NEW
    </span>
  );
}
