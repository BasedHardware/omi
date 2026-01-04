'use client';

import { useMemo, useState, useCallback } from 'react';
import type { Memory } from '@/types/conversation';

// Cluster colors - distinct colors for different tag groups
export const CLUSTER_COLORS = [
  '#8B5CF6', // Purple
  '#3B82F6', // Blue
  '#10B981', // Green/Emerald
  '#F59E0B', // Amber
  '#EF4444', // Red
  '#EC4899', // Pink
  '#06B6D4', // Cyan
  '#F97316', // Orange
];

// Tag with count and metadata
export interface TagInfo {
  name: string;
  count: number;
  relatedCount: number;
}

// Tag pair relationship
export interface TagRelationship {
  tag1: string;
  tag2: string;
  sharedCount: number;
  isCrossCluster: boolean;
}

// Theme cluster
export interface ThemeCluster {
  id: number;
  name: string;
  color: string;
  tags: string[];
  totalCount: number;
}

// Dashboard stats
export interface DashboardStats {
  totalTags: number;
  totalMemoriesWithTags: number;
  avgTagsPerMemory: number;
  topTag: string;
  topTagCount: number;
}

// Insight types
export interface TagInsight {
  type: 'theme' | 'connection' | 'isolated';
  title: string;
  description: string;
  tags: string[];
  count?: number;
}

export interface UseTagDashboardReturn {
  stats: DashboardStats | null;
  themes: ThemeCluster[];
  relationships: TagRelationship[];
  insights: TagInsight[];
  allTags: TagInfo[];
  // Search/filter
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  filteredTags: TagInfo[];
  // Selected
  selectedTags: string[];
  toggleTagSelection: (tag: string) => void;
  clearSelection: () => void;
}

// Simple union-find for clustering
class UnionFind {
  parent: Map<string, string>;
  rank: Map<string, number>;

  constructor(items: string[]) {
    this.parent = new Map();
    this.rank = new Map();
    items.forEach((item) => {
      this.parent.set(item, item);
      this.rank.set(item, 0);
    });
  }

  find(x: string): string {
    if (this.parent.get(x) !== x) {
      this.parent.set(x, this.find(this.parent.get(x)!));
    }
    return this.parent.get(x)!;
  }

  union(x: string, y: string): void {
    const rootX = this.find(x);
    const rootY = this.find(y);
    if (rootX === rootY) return;

    const rankX = this.rank.get(rootX) || 0;
    const rankY = this.rank.get(rootY) || 0;

    if (rankX < rankY) {
      this.parent.set(rootX, rootY);
    } else if (rankX > rankY) {
      this.parent.set(rootY, rootX);
    } else {
      this.parent.set(rootY, rootX);
      this.rank.set(rootX, rankX + 1);
    }
  }

  getClusters(): Map<string, string[]> {
    const clusters = new Map<string, string[]>();
    this.parent.forEach((_, item) => {
      const root = this.find(item);
      if (!clusters.has(root)) {
        clusters.set(root, []);
      }
      clusters.get(root)!.push(item);
    });
    return clusters;
  }
}

export function useTagDashboard(memories: Memory[]): UseTagDashboardReturn {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  // Calculate all dashboard data
  const { stats, themes, relationships, insights, allTags, tagCounts, connectionCounts } = useMemo(() => {
    if (!memories || memories.length === 0) {
      return {
        stats: null,
        themes: [],
        relationships: [],
        insights: [],
        allTags: [],
        tagCounts: new Map<string, number>(),
        connectionCounts: new Map<string, number>(),
      };
    }

    // Step 1: Count tag frequencies
    const tagCounts = new Map<string, number>();
    let memoriesWithTags = 0;
    let totalTagsUsed = 0;

    memories.forEach((memory) => {
      if (memory.tags && Array.isArray(memory.tags) && memory.tags.length > 0) {
        memoriesWithTags++;
        totalTagsUsed += memory.tags.length;
        memory.tags.forEach((tag) => {
          tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
        });
      }
    });

    if (tagCounts.size === 0) {
      return {
        stats: null,
        themes: [],
        relationships: [],
        insights: [],
        allTags: [],
        tagCounts: new Map<string, number>(),
        connectionCounts: new Map<string, number>(),
      };
    }

    // Step 2: Calculate co-occurrence
    const cooccurrence = new Map<string, Map<string, number>>();
    memories.forEach((memory) => {
      const tags = memory.tags || [];
      if (tags.length < 2) return;

      for (let i = 0; i < tags.length; i++) {
        for (let j = i + 1; j < tags.length; j++) {
          const tag1 = tags[i];
          const tag2 = tags[j];
          const [first, second] = tag1 < tag2 ? [tag1, tag2] : [tag2, tag1];

          if (!cooccurrence.has(first)) {
            cooccurrence.set(first, new Map());
          }
          const current = cooccurrence.get(first)!.get(second) || 0;
          cooccurrence.get(first)!.set(second, current + 1);
        }
      }
    });

    // Step 3: Build relationships list (sorted by count)
    const relationshipsList: TagRelationship[] = [];
    cooccurrence.forEach((innerMap, tag1) => {
      innerMap.forEach((count, tag2) => {
        if (count >= 2) {
          // Only include pairs with 2+ shared
          relationshipsList.push({
            tag1,
            tag2,
            sharedCount: count,
            isCrossCluster: false, // Will update after clustering
          });
        }
      });
    });
    relationshipsList.sort((a, b) => b.sharedCount - a.sharedCount);

    // Step 4: Cluster tags using Jaccard similarity
    const allTagNames = Array.from(tagCounts.keys());
    const uf = new UnionFind(allTagNames);

    cooccurrence.forEach((innerMap, tag1) => {
      innerMap.forEach((coCount, tag2) => {
        const count1 = tagCounts.get(tag1) || 0;
        const count2 = tagCounts.get(tag2) || 0;
        const union = count1 + count2 - coCount;
        const jaccard = union > 0 ? coCount / union : 0;

        if (jaccard > 0.25 && coCount >= 3) {
          uf.union(tag1, tag2);
        }
      });
    });

    // Build cluster data
    const rawClusters = uf.getClusters();
    const clusterData: { root: string; tags: string[]; totalCount: number }[] = [];

    rawClusters.forEach((tags, root) => {
      const totalCount = tags.reduce((sum, tag) => sum + (tagCounts.get(tag) || 0), 0);
      clusterData.push({ root, tags, totalCount });
    });

    clusterData.sort((a, b) => b.totalCount - a.totalCount);

    // Assign cluster indices
    const tagToCluster = new Map<string, number>();
    clusterData.forEach(({ tags }, index) => {
      tags.forEach((tag) => tagToCluster.set(tag, index));
    });

    // Update cross-cluster flag on relationships
    relationshipsList.forEach((rel) => {
      const cluster1 = tagToCluster.get(rel.tag1) ?? -1;
      const cluster2 = tagToCluster.get(rel.tag2) ?? -1;
      rel.isCrossCluster = cluster1 !== cluster2;
    });

    // Build theme clusters (top 8)
    const themesList: ThemeCluster[] = clusterData.slice(0, 8).map(({ tags, totalCount }, index) => {
      const sortedTags = [...tags].sort((a, b) => (tagCounts.get(b) || 0) - (tagCounts.get(a) || 0));
      return {
        id: index,
        name: sortedTags[0], // Top tag is the theme name
        color: CLUSTER_COLORS[index % CLUSTER_COLORS.length],
        tags: sortedTags.slice(0, 8), // Top 8 tags in cluster
        totalCount,
      };
    });

    // Step 5: Calculate connection counts for each tag
    const connectionCounts = new Map<string, number>();
    cooccurrence.forEach((innerMap, tag1) => {
      innerMap.forEach((_, tag2) => {
        connectionCounts.set(tag1, (connectionCounts.get(tag1) || 0) + 1);
        connectionCounts.set(tag2, (connectionCounts.get(tag2) || 0) + 1);
      });
    });

    // Build allTags list
    const allTagsList: TagInfo[] = allTagNames
      .map((name) => ({
        name,
        count: tagCounts.get(name) || 0,
        relatedCount: connectionCounts.get(name) || 0,
      }))
      .sort((a, b) => b.count - a.count);

    // Step 6: Calculate stats
    const sortedByCount = [...tagCounts.entries()].sort((a, b) => b[1] - a[1]);
    const [topTag, topTagCount] = sortedByCount[0] || ['', 0];

    const dashboardStats: DashboardStats = {
      totalTags: tagCounts.size,
      totalMemoriesWithTags: memoriesWithTags,
      avgTagsPerMemory: memoriesWithTags > 0 ? Math.round((totalTagsUsed / memoriesWithTags) * 10) / 10 : 0,
      topTag,
      topTagCount,
    };

    // Step 7: Generate insights
    const insightsList: TagInsight[] = [];

    // Top themes insight
    if (themesList.length > 0) {
      const topThemes = themesList.slice(0, 5);
      insightsList.push({
        type: 'theme',
        title: 'Your main themes',
        description: topThemes.map((t) => `${t.name} (${t.totalCount})`).join(', '),
        tags: topThemes.map((t) => t.name),
        count: topThemes.length,
      });
    }

    // Cross-cluster connections (surprising)
    const crossClusterRels = relationshipsList.filter((r) => r.isCrossCluster).slice(0, 5);
    crossClusterRels.forEach((rel) => {
      insightsList.push({
        type: 'connection',
        title: 'Surprising connection',
        description: `"${rel.tag1}" and "${rel.tag2}" appear together in ${rel.sharedCount} memories`,
        tags: [rel.tag1, rel.tag2],
        count: rel.sharedCount,
      });
    });

    // Isolated topics
    const isolatedTags = allTagsList
      .filter((tag) => tag.count >= 10 && tag.relatedCount <= 2)
      .slice(0, 3);

    if (isolatedTags.length > 0) {
      insightsList.push({
        type: 'isolated',
        title: 'Standalone topics',
        description: `These topics rarely connect to others: ${isolatedTags.map((t) => t.name).join(', ')}`,
        tags: isolatedTags.map((t) => t.name),
      });
    }

    return {
      stats: dashboardStats,
      themes: themesList,
      relationships: relationshipsList.slice(0, 50), // Top 50 relationships
      insights: insightsList,
      allTags: allTagsList,
      tagCounts,
      connectionCounts,
    };
  }, [memories]);

  // Filter tags by search
  const filteredTags = useMemo(() => {
    if (!searchQuery.trim()) return allTags;
    const lower = searchQuery.toLowerCase();
    return allTags.filter((t) => t.name.toLowerCase().includes(lower));
  }, [allTags, searchQuery]);

  // Toggle tag selection
  const toggleTagSelection = useCallback((tag: string) => {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  }, []);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelectedTags([]);
  }, []);

  return {
    stats,
    themes,
    relationships,
    insights,
    allTags,
    searchQuery,
    setSearchQuery,
    filteredTags,
    selectedTags,
    toggleTagSelection,
    clearSelection,
  };
}
