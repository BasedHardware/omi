'use client';

import { Star, Download } from 'lucide-react';
import Link from 'next/link';
import type { Plugin, PluginStat } from '../types';
import { NewBadge } from '../new-badge';

export interface CompactPluginCardProps {
  plugin: Plugin;
  stat?: PluginStat;
  index: number;
}

const formatInstalls = (num: number) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

export function CompactPluginCard({ plugin, index }: CompactPluginCardProps) {
  return (
    <Link
      href={`/apps/${plugin.id}`}
      className="group flex items-start gap-2.5 rounded-lg p-2 text-left transition-colors duration-300 hover:bg-[#1A1F2E]/50"
      data-plugin-card
      data-plugin-id={plugin.id}
      data-search-content={`${plugin.name} ${plugin.author} ${plugin.description}`}
      data-categories={plugin.category}
      data-capabilities={Array.from(plugin.capabilities).join(' ')}
    >
      {/* Index number */}
      <span className="flex w-4 shrink-0 items-center text-sm font-medium text-gray-400">
        {index}
      </span>

      {/* App icon */}
      <img
        src={plugin.image || 'https://via.placeholder.com/40'}
        alt={plugin.name}
        className="h-11 w-11 shrink-0 rounded-lg object-cover sm:h-14 sm:w-14"
      />

      {/* Content */}
      <div className="min-w-0 flex-1 space-y-0.5">
        {/* Title and NEW badge */}
        <div className="flex items-center gap-2">
          <h3 className="flex-1 truncate font-medium text-white transition-colors group-hover:text-[#6C8EEF]">
            {plugin.name}
          </h3>
          <NewBadge plugin={plugin} />
        </div>

        {/* Author and Stats Row */}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-gray-400">by {plugin.author}</span>
          <div className="flex shrink-0 items-center gap-2.5 text-xs text-gray-400">
            <div className="flex items-center">
              <Star className="mr-1 h-3.5 w-3.5" />
              <span>{plugin.rating_avg?.toFixed(1)}</span>
            </div>
            <div className="flex items-center">
              <Download className="mr-1 h-3 w-3" />
              <span>{formatInstalls(plugin.installs)}</span>
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="line-clamp-1 text-xs text-gray-400 transition-colors group-hover:text-gray-300 sm:text-sm">
          {plugin.description}
        </p>
      </div>
    </Link>
  );
}
