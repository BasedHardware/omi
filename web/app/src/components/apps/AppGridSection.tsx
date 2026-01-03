'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { App } from '@/types/apps';
import { AppCard } from './AppCard';

interface AppGridSectionProps {
  title: string;
  apps: App[];
  totalCount?: number;
  capabilityId?: string;
  onUpdate?: () => void;
}

export function AppGridSection({
  title,
  apps,
  totalCount,
  capabilityId,
  onUpdate,
}: AppGridSectionProps) {
  const showViewAll = totalCount && totalCount > apps.length;

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
        {showViewAll && capabilityId && (
          <Link
            href={`/apps?capability=${capabilityId}`}
            className={cn(
              'flex items-center gap-1 text-sm text-purple-primary',
              'hover:underline'
            )}
          >
            View all ({totalCount})
            <ChevronRight className="w-4 h-4" />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {apps.map(app => (
          <AppCard key={app.id} app={app} onUpdate={onUpdate} />
        ))}
      </div>
    </section>
  );
}
