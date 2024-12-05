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
      className="flex items-start gap-4 rounded-lg p-2 text-left transition-colors duration-300 hover:bg-[#1A1F2E]/50"
      data-plugin-card
      data-search-content={`${plugin.name} ${plugin.author} ${plugin.description}`}
      data-categories={plugin.category}
      data-capabilities={Array.from(plugin.capabilities).join(' ')}
    >
      {/* Index number */}
      <span className="w-6 text-sm font-medium text-gray-400">{index}</span>

      {/* App icon */}
      <img
        src={plugin.image || 'https://via.placeholder.com/40'}
        alt={plugin.name}
        className="h-14 w-14 rounded-lg object-cover"
      />

      {/* Content */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {/* Title and NEW badge */}
        <div className="flex items-center gap-2">
          <h3 className="flex-1 truncate font-medium text-white">{plugin.name}</h3>
          <NewBadge plugin={plugin} />
        </div>

        {/* Author and Stats Row */}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-gray-400">by {plugin.author}</span>
          <div className="flex shrink-0 items-center gap-4 text-xs text-gray-400">
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
        <p className="line-clamp-1 text-sm text-gray-400">{plugin.description}</p>
      </div>
    </Link>
  );
}
