/* eslint-disable prettier/prettier */
'use client';

import { type Plugin } from './types';

// Utility function to check if an app is new (within 7 days)
export function isNewApp(plugin: Plugin): boolean {
  if (!plugin.created_at) return false;
  try {
    const creationDate = new Date(plugin.created_at);
    const now = new Date();
    // Validate the date
    if (isNaN(creationDate.getTime())) return false;
    const diffInDays = Math.floor(
      (now.getTime() - creationDate.getTime()) / (1000 * 60 * 60 * 24)
    );
    // Add debug logging in development
    if (process.env.NODE_ENV === 'development') {
      console.log('Plugin:', plugin.name);
      console.log('Creation date:', plugin.created_at);
      console.log('Diff in days:', diffInDays);
    }

    return diffInDays <= 7;
  } catch (e) {
    console.error('Error parsing date for plugin:', plugin.name, e);
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
