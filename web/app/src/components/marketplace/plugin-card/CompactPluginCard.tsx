'use client';

import { memo } from 'react';
import { Star, Download } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import type { Plugin } from '../types';
import { NewBadge } from '../NewBadge';
import { formatInstalls } from '../utils/format';

export interface CompactPluginCardProps {
  plugin: Plugin;
  index: number;
}

export const CompactPluginCard = memo(function CompactPluginCard({
  plugin,
  index,
}: CompactPluginCardProps) {
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
      <Image
        src={plugin.image || 'https://via.placeholder.com/40'}
        alt={plugin.name}
        className="h-11 w-11 shrink-0 rounded-lg object-cover sm:h-14 sm:w-14"
        width={56}
        height={56}
      />

      {/* Content */}
      <div className="min-w-0 flex-1 space-y-0.5">
        {/* Title, Paid badge, and NEW badge */}
        <div className="flex items-center gap-2">
          <h3 className="flex-1 truncate font-medium text-white transition-colors group-hover:text-[#6C8EEF]">
            {plugin.name}
          </h3>
          {plugin.is_paid && (
            <span className="inline-flex shrink-0 items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-xs font-medium text-amber-400">
              ${plugin.price?.toFixed(2)}
              {plugin.payment_plan === 'monthly_recurring' ? '/mo' : ''}
            </span>
          )}
          <NewBadge plugin={plugin} />
        </div>

        {/* Author and Stats Row */}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-gray-400">by {plugin.author}</span>
          <div className="flex shrink-0 items-center gap-2.5 text-xs text-gray-400">
            {plugin.rating_count > 0 && (
              <div className="flex items-center">
                <Star className="mr-1 h-3.5 w-3.5 fill-yellow-400 text-yellow-400" />
                <span>{plugin.rating_avg?.toFixed(1)}</span>
              </div>
            )}
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
});
