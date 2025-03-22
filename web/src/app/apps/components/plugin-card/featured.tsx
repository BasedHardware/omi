'use client';

import { Star, Download } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import type { Plugin, PluginStat } from '../types';
import { NewBadge } from '../new-badge';

export interface FeaturedPluginCardProps {
  plugin: Plugin;
  stat?: PluginStat;
  hideStats?: boolean;
}

const formatInstalls = (num: number) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

export function FeaturedPluginCard({ plugin, hideStats }: FeaturedPluginCardProps) {
  return (
    <Link
      href={`/apps/${plugin.id}`}
      className="group relative block h-full overflow-hidden rounded-xl bg-[#1A1F2E]"
      data-plugin-card
      data-search-content={`${plugin.name} ${plugin.author} ${plugin.description}`}
      data-categories={plugin.category}
      data-capabilities={Array.from(plugin.capabilities).join(' ')}
    >
      {/* Image */}
      <div className="aspect-[16/9] w-full overflow-hidden">
        <Image
          src={plugin.image || 'https://via.placeholder.com/400x225'}
          alt={plugin.name}
          width={400}
          height={225}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          priority
        />
      </div>

      {/* Content */}
      <div className="flex h-[9.5rem] flex-col gap-1.5 p-3 sm:h-[10.5rem] sm:gap-2 sm:p-4">
        {/* Title and NEW badge */}
        <div className="flex items-center gap-2">
          <h3 className="line-clamp-1 flex-1 text-base font-medium text-white sm:text-lg">
            {plugin.name}
          </h3>
          <NewBadge plugin={plugin} />
        </div>

        {/* Author Row */}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-gray-400 sm:text-sm">
            by {plugin.author}
          </span>
          {!hideStats && (
            <div className="flex shrink-0 items-center gap-3 text-xs text-gray-400 sm:gap-4 sm:text-sm">
              <div className="flex items-center">
                <Star className="mr-1 h-3.5 w-3.5 sm:h-4 sm:w-4" />
                <span>{plugin.rating_avg?.toFixed(1) || '0.0'}</span>
              </div>
              <div className="flex items-center">
                <Download className="mr-1 h-3.5 w-3.5 sm:h-4 sm:w-4" />
                <span>{formatInstalls(plugin.installs)}</span>
              </div>
            </div>
          )}
        </div>

        {/* Description */}
        <p className="mt-auto line-clamp-2 text-xs text-gray-400 sm:text-sm">
          {plugin.description}
        </p>
      </div>
    </Link>
  );
}
