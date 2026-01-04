'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Tag,
  Search,
  Link2,
  Lightbulb,
  ChevronRight,
  ArrowUpDown,
  Circle,
  TrendingUp,
  Hash,
  BarChart3,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTagDashboard, CLUSTER_COLORS, type ThemeCluster, type TagRelationship } from '@/hooks/useTagDashboard';
import type { Memory } from '@/types/conversation';

interface TagDashboardProps {
  memories: Memory[];
  onTagSelect?: (tags: string[]) => void;
}

type SortField = 'count' | 'name' | 'related';
type SortDirection = 'asc' | 'desc';

export function TagDashboard({ memories, onTagSelect }: TagDashboardProps) {
  const {
    stats,
    themes,
    relationships,
    insights,
    allTags,
    searchQuery,
    setSearchQuery,
    filteredTags,
  } = useTagDashboard(memories);

  const [sortField, setSortField] = useState<SortField>('count');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [showAllRelationships, setShowAllRelationships] = useState(false);

  // Sort tags
  const sortedTags = [...filteredTags].sort((a, b) => {
    const multiplier = sortDirection === 'desc' ? -1 : 1;
    switch (sortField) {
      case 'name':
        return multiplier * a.name.localeCompare(b.name);
      case 'related':
        return multiplier * (a.relatedCount - b.relatedCount);
      default:
        return multiplier * (a.count - b.count);
    }
  });

  // Toggle sort
  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'desc' ? 'asc' : 'desc'));
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  // Handle theme click
  const handleThemeClick = (theme: ThemeCluster) => {
    if (onTagSelect) {
      onTagSelect(theme.tags.slice(0, 5));
    }
  };

  // Handle relationship click
  const handleRelationshipClick = (rel: TagRelationship) => {
    if (onTagSelect) {
      onTagSelect([rel.tag1, rel.tag2]);
    }
  };

  // Handle single tag click
  const handleTagClick = (tag: string) => {
    if (onTagSelect) {
      onTagSelect([tag]);
    }
  };

  // Empty state
  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <div className="w-20 h-20 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
          <Tag className="w-10 h-10 text-text-quaternary" />
        </div>
        <h3 className="text-lg font-medium text-text-primary mb-2">No tags found</h3>
        <p className="text-sm text-text-tertiary max-w-sm">
          Your memories don&apos;t have any tags yet. Tags help organize and discover patterns in your memories.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-8">
        {/* Stats Overview */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={Hash} label="Total Tags" value={stats.totalTags.toLocaleString()} />
          <StatCard icon={BarChart3} label="Tagged Memories" value={stats.totalMemoriesWithTags.toLocaleString()} />
          <StatCard icon={TrendingUp} label="Avg Tags/Memory" value={stats.avgTagsPerMemory.toString()} />
          <StatCard
            icon={Tag}
            label="Top Tag"
            value={stats.topTag}
            subValue={`${stats.topTagCount} memories`}
          />
        </div>

        {/* Insights */}
        {insights.length > 0 && (
          <section>
            <SectionHeader icon={Lightbulb} title="Insights" iconColor="text-amber-400" />
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {insights.slice(0, 6).map((insight, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className={cn(
                    'p-4 rounded-xl border',
                    'bg-bg-secondary border-bg-tertiary',
                    'hover:border-bg-quaternary transition-colors'
                  )}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {insight.type === 'theme' && <Circle className="w-3 h-3 text-purple-primary fill-current" />}
                    {insight.type === 'connection' && <Link2 className="w-3 h-3 text-blue-400" />}
                    {insight.type === 'isolated' && <Circle className="w-3 h-3 text-amber-400" />}
                    <span className="text-xs font-medium text-text-secondary">{insight.title}</span>
                  </div>
                  <p className="text-sm text-text-tertiary">{insight.description}</p>
                </motion.div>
              ))}
            </div>
          </section>
        )}

        {/* Themes */}
        {themes.length > 0 && (
          <section>
            <SectionHeader icon={Tag} title="Your Themes" />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {themes.map((theme, index) => (
                <motion.button
                  key={theme.id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: index * 0.05 }}
                  onClick={() => handleThemeClick(theme)}
                  className={cn(
                    'p-4 rounded-xl border text-left',
                    'bg-bg-secondary border-bg-tertiary',
                    'hover:border-bg-quaternary hover:bg-bg-tertiary/50',
                    'transition-all group'
                  )}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: theme.color }}
                    />
                    <span className="font-medium text-text-primary truncate">{theme.name}</span>
                    <ChevronRight className="w-4 h-4 text-text-quaternary ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <p className="text-xs text-text-quaternary mb-2">{theme.totalCount} memories</p>
                  <div className="flex flex-wrap gap-1">
                    {theme.tags.slice(1, 5).map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 rounded text-xs bg-bg-tertiary text-text-tertiary"
                      >
                        {tag}
                      </span>
                    ))}
                    {theme.tags.length > 5 && (
                      <span className="px-2 py-0.5 text-xs text-text-quaternary">
                        +{theme.tags.length - 5}
                      </span>
                    )}
                  </div>
                </motion.button>
              ))}
            </div>
          </section>
        )}

        {/* Top Relationships */}
        {relationships.length > 0 && (
          <section>
            <SectionHeader icon={Link2} title="Tag Relationships" />
            <div className="rounded-xl border border-bg-tertiary overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-bg-secondary border-b border-bg-tertiary">
                    <th className="px-4 py-3 text-left text-xs font-medium text-text-quaternary uppercase tracking-wider">
                      Tag 1
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-text-quaternary uppercase tracking-wider">
                      Tag 2
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-text-quaternary uppercase tracking-wider">
                      Shared
                    </th>
                    <th className="px-4 py-3 w-20"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-bg-tertiary">
                  {(showAllRelationships ? relationships : relationships.slice(0, 10)).map((rel, index) => (
                    <tr
                      key={`${rel.tag1}-${rel.tag2}`}
                      className="bg-bg-primary hover:bg-bg-secondary transition-colors"
                    >
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleTagClick(rel.tag1)}
                          className="text-sm text-text-primary hover:text-purple-primary transition-colors"
                        >
                          {rel.tag1}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleTagClick(rel.tag2)}
                          className="text-sm text-text-primary hover:text-purple-primary transition-colors"
                        >
                          {rel.tag2}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-sm text-text-secondary">{rel.sharedCount}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleRelationshipClick(rel)}
                          className="text-xs text-purple-primary hover:text-purple-secondary transition-colors"
                        >
                          Filter
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {relationships.length > 10 && (
                <div className="p-3 bg-bg-secondary border-t border-bg-tertiary">
                  <button
                    onClick={() => setShowAllRelationships(!showAllRelationships)}
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors"
                  >
                    {showAllRelationships ? 'Show less' : `Show all ${relationships.length} relationships`}
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* All Tags */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <SectionHeader icon={Hash} title="All Tags" className="mb-0" />
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-quaternary" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search tags..."
                className={cn(
                  'pl-9 pr-4 py-2 rounded-lg w-64',
                  'bg-bg-secondary border border-bg-tertiary',
                  'text-sm text-text-primary',
                  'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
                  'placeholder:text-text-quaternary'
                )}
              />
            </div>
          </div>

          {/* Sort buttons */}
          <div className="flex gap-2 mb-4">
            <SortButton
              label="Count"
              active={sortField === 'count'}
              direction={sortField === 'count' ? sortDirection : undefined}
              onClick={() => toggleSort('count')}
            />
            <SortButton
              label="Name"
              active={sortField === 'name'}
              direction={sortField === 'name' ? sortDirection : undefined}
              onClick={() => toggleSort('name')}
            />
            <SortButton
              label="Related"
              active={sortField === 'related'}
              direction={sortField === 'related' ? sortDirection : undefined}
              onClick={() => toggleSort('related')}
            />
          </div>

          {/* Tags grid */}
          <div className="flex flex-wrap gap-2">
            {sortedTags.slice(0, 100).map((tag) => (
              <button
                key={tag.name}
                onClick={() => handleTagClick(tag.name)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
                  'bg-bg-secondary border border-bg-tertiary',
                  'hover:border-purple-primary/50 hover:bg-bg-tertiary',
                  'transition-all text-sm group'
                )}
              >
                <span className="text-text-primary group-hover:text-purple-primary transition-colors">
                  {tag.name}
                </span>
                <span className="text-text-quaternary text-xs">({tag.count})</span>
              </button>
            ))}
            {sortedTags.length > 100 && (
              <span className="inline-flex items-center px-3 py-1.5 text-sm text-text-quaternary">
                +{sortedTags.length - 100} more
              </span>
            )}
          </div>
          {filteredTags.length === 0 && searchQuery && (
            <p className="text-center text-text-quaternary py-8">No tags match &quot;{searchQuery}&quot;</p>
          )}
        </section>
      </div>
    </div>
  );
}

// Stat card component
function StatCard({
  icon: Icon,
  label,
  value,
  subValue,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  subValue?: string;
}) {
  return (
    <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4 text-text-quaternary" />
        <span className="text-xs text-text-quaternary">{label}</span>
      </div>
      <p className="text-xl font-semibold text-text-primary truncate">{value}</p>
      {subValue && <p className="text-xs text-text-tertiary mt-0.5">{subValue}</p>}
    </div>
  );
}

// Section header component
function SectionHeader({
  icon: Icon,
  title,
  iconColor = 'text-purple-primary',
  className,
}: {
  icon: React.ElementType;
  title: string;
  iconColor?: string;
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-2 mb-4', className)}>
      <Icon className={cn('w-5 h-5', iconColor)} />
      <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
    </div>
  );
}

// Sort button component
function SortButton({
  label,
  active,
  direction,
  onClick,
}: {
  label: string;
  active: boolean;
  direction?: 'asc' | 'desc';
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm',
        'border transition-colors',
        active
          ? 'bg-purple-primary/10 border-purple-primary/50 text-purple-primary'
          : 'bg-bg-secondary border-bg-tertiary text-text-secondary hover:text-text-primary'
      )}
    >
      {label}
      {active && (
        <ArrowUpDown
          className={cn('w-3 h-3', direction === 'asc' && 'rotate-180')}
        />
      )}
    </button>
  );
}
