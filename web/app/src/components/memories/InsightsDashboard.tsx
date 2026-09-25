'use client';

import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, TrendingUp, TrendingDown, Search, Tag } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type LifeBalanceData,
  type TrendingTag,
  type ActivityDay,
  type UseInsightsDashboardReturn,
} from '@/hooks/useInsightsDashboard';

interface InsightsDashboardProps {
  insights: UseInsightsDashboardReturn;
  onTagSelect?: (tags: string[]) => void;
}

const MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

export function InsightsDashboard({ insights, onTagSelect }: InsightsDashboardProps) {
  const { summary, activityCalendar, allTags, computing } = insights;

  const [searchQuery, setSearchQuery] = useState('');

  // Filter tags by search
  const filteredTags = useMemo(() => {
    if (!searchQuery.trim()) return allTags.slice(0, 50);
    const lower = searchQuery.toLowerCase();
    return allTags.filter((t) => t.tag.toLowerCase().includes(lower)).slice(0, 50);
  }, [allTags, searchQuery]);

  // Handle tag click
  const handleTagClick = (tag: string) => {
    if (onTagSelect) {
      onTagSelect([tag]);
    }
  };

  // Loading state (computing insights in Web Worker)
  if (computing) {
    return (
      <div className="h-full w-full max-w-full overflow-y-auto">
        <div className="mx-auto w-full max-w-full space-y-6 p-6 lg:max-w-5xl">
          {/* Skeleton for Activity Calendar */}
          <div className="animate-pulse rounded-2xl border border-bg-tertiary bg-bg-secondary p-6">
            <div className="mb-4 h-4 w-24 rounded bg-bg-tertiary"></div>
            <div className="h-32 rounded bg-bg-tertiary"></div>
          </div>

          {/* Skeleton for Tags */}
          <div className="animate-pulse rounded-2xl border border-bg-tertiary bg-bg-secondary p-6">
            <div className="mb-4 h-4 w-32 rounded bg-bg-tertiary"></div>
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="h-8 rounded bg-bg-tertiary"></div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (!summary) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center">
        <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-bg-tertiary">
          <Sparkles className="h-10 w-10 text-text-quaternary" />
        </div>
        <h3 className="mb-2 text-lg font-medium text-text-primary">No insights yet</h3>
        <p className="max-w-sm text-sm text-text-tertiary">
          Add more memories to see insights about your life patterns and themes.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full w-full max-w-full overflow-y-auto">
      <div className="mx-auto w-full max-w-full space-y-6 p-6 lg:max-w-5xl">
        {/* Activity Calendar */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-bg-tertiary bg-bg-secondary p-6"
        >
          <h2 className="mb-4 text-sm font-medium text-text-tertiary">ACTIVITY</h2>
          <ActivityHeatmap data={activityCalendar} />
        </motion.div>

        {/* All Tags */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-2xl border border-bg-tertiary bg-bg-secondary p-6"
        >
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Tag className="h-4 w-4 text-white" />
              <h2 className="text-sm font-medium text-text-tertiary">ALL TAGS</h2>
              <span className="text-xs text-text-quaternary">({allTags.length})</span>
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-quaternary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search tags..."
                className={cn(
                  'w-48 rounded-lg py-1.5 pl-9 pr-4',
                  'border border-bg-quaternary bg-bg-tertiary',
                  'text-sm text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-white/50',
                  'placeholder:text-text-quaternary',
                )}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {filteredTags.map((t) => (
              <button
                key={t.tag}
                onClick={() => handleTagClick(t.tag)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5',
                  'border border-bg-quaternary bg-bg-tertiary',
                  'hover:border-white/50 hover:bg-white/10',
                  'group text-sm transition-all',
                )}
              >
                <span className="text-text-primary transition-colors group-hover:text-white">
                  {t.tag}
                </span>
                <span className="text-xs text-text-quaternary">({t.count})</span>
              </button>
            ))}
            {allTags.length > 50 && !searchQuery && (
              <span className="inline-flex items-center px-3 py-1.5 text-sm text-text-quaternary">
                +{allTags.length - 50} more
              </span>
            )}
          </div>
          {filteredTags.length === 0 && searchQuery && (
            <p className="py-4 text-center text-text-quaternary">
              No tags match &quot;{searchQuery}&quot;
            </p>
          )}
        </motion.div>
      </div>
    </div>
  );
}

// ==================== EXPORTED SIDEBAR COMPONENTS ====================

// Life Balance Radar Chart (SVG) - Compact version for sidebar
export function LifeBalanceChart({
  data,
  compact = false,
}: {
  data: LifeBalanceData[];
  compact?: boolean;
}) {
  if (data.length === 0) return null;

  const size = compact ? 160 : 200;
  const center = size / 2;
  const maxRadius = compact ? 60 : 80;

  // Calculate points for each category
  const points = data.map((d, i) => {
    const angle = (i / data.length) * 2 * Math.PI - Math.PI / 2;
    const radius = (d.value / 100) * maxRadius;
    return {
      x: center + radius * Math.cos(angle),
      y: center + radius * Math.sin(angle),
      labelX: center + (maxRadius + (compact ? 16 : 20)) * Math.cos(angle),
      labelY: center + (maxRadius + (compact ? 16 : 20)) * Math.sin(angle),
      ...d,
    };
  });

  // Create polygon path
  const polygonPath =
    points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z';

  // Background grid circles
  const gridCircles = [0.25, 0.5, 0.75, 1].map((scale) => maxRadius * scale);

  return (
    <div className="flex items-center justify-center">
      <svg width={size} height={size} className="overflow-visible">
        {/* Grid circles */}
        {gridCircles.map((r, i) => (
          <circle
            key={i}
            cx={center}
            cy={center}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            className="text-bg-quaternary"
            strokeDasharray={i < 3 ? '2 2' : undefined}
          />
        ))}

        {/* Grid lines */}
        {points.map((p, i) => (
          <line
            key={i}
            x1={center}
            y1={center}
            x2={
              center + maxRadius * Math.cos((i / data.length) * 2 * Math.PI - Math.PI / 2)
            }
            y2={
              center + maxRadius * Math.sin((i / data.length) * 2 * Math.PI - Math.PI / 2)
            }
            stroke="currentColor"
            strokeWidth="1"
            className="text-bg-quaternary"
          />
        ))}

        {/* Data polygon */}
        <path
          d={polygonPath}
          fill="url(#radarGradient)"
          stroke="#8B5CF6"
          strokeWidth="2"
          opacity="0.8"
        />

        {/* Gradient definition */}
        <defs>
          <linearGradient id="radarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.3" />
          </linearGradient>
        </defs>

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={compact ? 3 : 4}
            fill={p.color}
            stroke="#0F0F0F"
            strokeWidth="2"
          />
        ))}

        {/* Labels */}
        {points.map((p, i) => (
          <text
            key={i}
            x={p.labelX}
            y={p.labelY}
            textAnchor="middle"
            dominantBaseline="middle"
            className={cn('fill-text-secondary', compact ? 'text-[10px]' : 'text-xs')}
          >
            {p.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

// Trending Tag Row - for sidebar use
export function TrendingTagRow({
  tag,
  isRising,
  onClick,
}: {
  tag: TrendingTag;
  isRising: boolean;
  onClick?: () => void;
}) {
  const changeText =
    tag.daysSinceLastMention && tag.daysSinceLastMention >= 14
      ? `${tag.daysSinceLastMention}d ago`
      : `${tag.change > 0 ? '+' : ''}${tag.change}%`;

  return (
    <button
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
    >
      <span className="text-sm text-text-primary">{tag.tag}</span>
      <span
        className={cn(
          'text-xs font-medium',
          isRising ? 'text-emerald-400' : 'text-rose-400',
        )}
      >
        {changeText}
      </span>
    </button>
  );
}

// Trending Section - Compact version for sidebar
export function TrendingSidebar({
  risingTags,
  fadingTags,
  onTagClick,
}: {
  risingTags: TrendingTag[];
  fadingTags: TrendingTag[];
  onTagClick?: (tag: string) => void;
}) {
  if (risingTags.length === 0 && fadingTags.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {/* Rising */}
      {risingTags.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-xs font-medium text-emerald-400">Rising</span>
          </div>
          <div className="space-y-1">
            {risingTags.slice(0, 3).map((tag) => (
              <TrendingTagRow
                key={tag.tag}
                tag={tag}
                isRising
                onClick={() => onTagClick?.(tag.tag)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Fading */}
      {fadingTags.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-1.5">
            <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
            <span className="text-xs font-medium text-rose-400">Fading</span>
          </div>
          <div className="space-y-1">
            {fadingTags.slice(0, 3).map((tag) => (
              <TrendingTagRow
                key={tag.tag}
                tag={tag}
                isRising={false}
                onClick={() => onTagClick?.(tag.tag)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== INTERNAL COMPONENTS ====================

// Activity Heatmap
function ActivityHeatmap({ data }: { data: ActivityDay[] }) {
  if (data.length === 0) return null;

  // Group by week
  const weeks: ActivityDay[][] = [];
  let currentWeek: ActivityDay[] = [];

  data.forEach((day) => {
    if (day.dayOfWeek === 0 && currentWeek.length > 0) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
    currentWeek.push(day);
  });
  if (currentWeek.length > 0) weeks.push(currentWeek);

  // Find max count for color scaling
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  // Get intensity color
  const getColor = (count: number) => {
    if (count === 0) return 'bg-bg-tertiary';
    const intensity = count / maxCount;
    if (intensity < 0.25) return 'bg-white/20';
    if (intensity < 0.5) return 'bg-white/40';
    if (intensity < 0.75) return 'bg-white/60';
    return 'bg-white';
  };

  // Month labels
  const monthLabels: { month: string; weekIdx: number }[] = [];
  let lastMonth = -1;
  data.forEach((day) => {
    const month = new Date(day.date).getMonth();
    if (month !== lastMonth) {
      lastMonth = month;
      monthLabels.push({ month: MONTH_NAMES[month], weekIdx: day.weekNumber });
    }
  });

  return (
    <div className="overflow-x-auto">
      {/* Month labels */}
      <div className="mb-1 ml-8 flex">
        {monthLabels.map((label, idx) => (
          <div
            key={idx}
            className="text-xs text-text-quaternary"
            style={{
              marginLeft:
                idx === 0
                  ? 0
                  : `${(label.weekIdx - monthLabels[idx - 1].weekIdx) * 12 - 20}px`,
            }}
          >
            {label.month}
          </div>
        ))}
      </div>

      <div className="flex gap-0.5">
        {/* Day labels */}
        <div className="mr-1 flex flex-col gap-0.5 text-xs text-text-quaternary">
          <div className="h-[10px]"></div>
          <div className="h-[10px] leading-[10px]">M</div>
          <div className="h-[10px]"></div>
          <div className="h-[10px] leading-[10px]">W</div>
          <div className="h-[10px]"></div>
          <div className="h-[10px] leading-[10px]">F</div>
          <div className="h-[10px]"></div>
        </div>

        {/* Weeks */}
        {weeks.map((week, weekIdx) => (
          <div key={weekIdx} className="flex flex-col gap-0.5">
            {[0, 1, 2, 3, 4, 5, 6].map((dayOfWeek) => {
              const day = week.find((d) => d.dayOfWeek === dayOfWeek);
              return (
                <div
                  key={dayOfWeek}
                  className={cn(
                    'h-[10px] w-[10px] rounded-sm',
                    day ? getColor(day.count) : 'bg-transparent',
                  )}
                  title={day ? `${day.date}: ${day.count} memories` : undefined}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-2 text-xs text-text-quaternary">
        <span>Less</span>
        <div className="flex gap-0.5">
          <div className="h-[10px] w-[10px] rounded-sm bg-bg-tertiary" />
          <div className="h-[10px] w-[10px] rounded-sm bg-white/20" />
          <div className="h-[10px] w-[10px] rounded-sm bg-white/40" />
          <div className="h-[10px] w-[10px] rounded-sm bg-white/60" />
          <div className="h-[10px] w-[10px] rounded-sm bg-white" />
        </div>
        <span>More</span>
      </div>
    </div>
  );
}
