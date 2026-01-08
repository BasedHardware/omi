'use client';

import { useMemo } from 'react';
import type { Memory } from '@/types/conversation';

// Life balance categories with keywords for auto-categorization
export const LIFE_CATEGORIES = {
  work: [
    'work',
    'meeting',
    'team',
    'project',
    'hiring',
    'company',
    'office',
    'client',
    'deadline',
    'presentation',
    'employee',
    'manager',
    'boss',
    'job',
    'career',
    'business',
    'sales',
    'marketing',
    'product',
    'engineering',
    'startup',
    'investor',
    'funding',
    'revenue',
  ],
  family: [
    'family',
    'kids',
    'children',
    'son',
    'daughter',
    'spouse',
    'wife',
    'husband',
    'home',
    'parent',
    'mom',
    'dad',
    'mother',
    'father',
    'sister',
    'brother',
    'grandma',
    'grandpa',
    'baby',
    'toddler',
  ],
  health: [
    'health',
    'gym',
    'workout',
    'exercise',
    'sleep',
    'diet',
    'meditation',
    'doctor',
    'fitness',
    'running',
    'yoga',
    'weight',
    'nutrition',
    'mental',
    'therapy',
    'stress',
    'anxiety',
    'wellness',
  ],
  learning: [
    'learn',
    'study',
    'course',
    'book',
    'read',
    'AI',
    'skill',
    'education',
    'training',
    'tutorial',
    'research',
    'knowledge',
    'coding',
    'programming',
    'language',
    'certificate',
    'degree',
  ],
  social: [
    'friend',
    'dinner',
    'party',
    'event',
    'social',
    'hangout',
    'call',
    'catch up',
    'lunch',
    'coffee',
    'drinks',
    'birthday',
    'wedding',
    'celebration',
    'network',
    'community',
  ],
  hobbies: [
    'travel',
    'vacation',
    'music',
    'game',
    'hobby',
    'sport',
    'movie',
    'show',
    'art',
    'photography',
    'cooking',
    'garden',
    'hiking',
    'camping',
    'beach',
    'concert',
    'museum',
    'theater',
  ],
} as const;

export type LifeCategory = keyof typeof LIFE_CATEGORIES;

// Category colors
export const CATEGORY_COLORS: Record<LifeCategory, string> = {
  work: '#8B5CF6', // Purple
  family: '#EC4899', // Pink
  health: '#10B981', // Green
  learning: '#3B82F6', // Blue
  social: '#F59E0B', // Amber
  hobbies: '#06B6D4', // Cyan
};

// Types
export interface SummaryStats {
  totalMemories: number;
  memoriesThisMonth: number;
  topTags: { tag: string; count: number }[];
  mostActiveDay: string;
  currentStreak: number;
  avgMemoriesPerDay: number;
  surprisingConnection?: { tag1: string; tag2: string; count: number };
}

export interface LifeBalanceData {
  category: LifeCategory;
  label: string;
  value: number; // 0-100 normalized
  rawCount: number;
  color: string;
}

export interface TrendingTag {
  tag: string;
  recentCount: number;
  priorCount: number;
  change: number; // percentage change
  daysSinceLastMention?: number;
}

export interface ActivityDay {
  date: string;
  count: number;
  dayOfWeek: number;
  weekNumber: number;
}

export interface TimePattern {
  label: string;
  count: number;
  percentage: number;
}

export interface UseInsightsDashboardReturn {
  summary: SummaryStats | null;
  lifeBalance: LifeBalanceData[];
  risingTags: TrendingTag[];
  fadingTags: TrendingTag[];
  activityCalendar: ActivityDay[];
  dayOfWeekPattern: TimePattern[];
  hourPattern: TimePattern[];
  allTags: { tag: string; count: number }[];
}

// Helper: Get day of week name
const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Helper: Calculate streak
function calculateStreak(memories: Memory[]): number {
  if (memories.length === 0) return 0;

  // Sort by date descending
  const sorted = [...memories].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let streak = 0;
  let currentDate = today;

  // Group memories by date
  const memoryDates = new Set(sorted.map((m) => m.created_at.split('T')[0]));

  // Check if today has memories, if not start from yesterday
  const todayStr = today.toISOString().split('T')[0];
  if (!memoryDates.has(todayStr)) {
    currentDate = new Date(today);
    currentDate.setDate(currentDate.getDate() - 1);
  }

  // Count consecutive days
  while (true) {
    const dateStr = currentDate.toISOString().split('T')[0];
    if (memoryDates.has(dateStr)) {
      streak++;
      currentDate.setDate(currentDate.getDate() - 1);
    } else {
      break;
    }
  }

  return streak;
}

// Helper: Categorize a tag
function categorizeTag(tag: string): LifeCategory | null {
  const lowerTag = tag.toLowerCase();

  for (const [category, keywords] of Object.entries(LIFE_CATEGORIES)) {
    for (const keyword of keywords) {
      if (lowerTag.includes(keyword.toLowerCase())) {
        return category as LifeCategory;
      }
    }
  }

  return null;
}

export function useInsightsDashboard(memories: Memory[]): UseInsightsDashboardReturn {
  return useMemo(() => {
    if (!memories || memories.length === 0) {
      return {
        summary: null,
        lifeBalance: [],
        risingTags: [],
        fadingTags: [],
        activityCalendar: [],
        dayOfWeekPattern: [],
        hourPattern: [],
        allTags: [],
      };
    }

    const now = new Date();
    const thirtyDaysAgo = new Date(now);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    const sixtyDaysAgo = new Date(now);
    sixtyDaysAgo.setDate(sixtyDaysAgo.getDate() - 60);

    // Start of current month
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    // ==================== TAG COUNTS ====================
    const tagCounts = new Map<string, number>();
    const tagLastSeen = new Map<string, Date>();
    const recentTagCounts = new Map<string, number>(); // Last 30 days
    const priorTagCounts = new Map<string, number>(); // 30-60 days ago

    // Co-occurrence for surprising connections
    const cooccurrence = new Map<string, Map<string, number>>();

    memories.forEach((memory) => {
      const createdAt = new Date(memory.created_at);
      const tags = memory.tags || [];

      tags.forEach((tag) => {
        // Total counts
        tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);

        // Last seen
        const lastSeen = tagLastSeen.get(tag);
        if (!lastSeen || createdAt > lastSeen) {
          tagLastSeen.set(tag, createdAt);
        }

        // Period counts for trending
        if (createdAt >= thirtyDaysAgo) {
          recentTagCounts.set(tag, (recentTagCounts.get(tag) || 0) + 1);
        } else if (createdAt >= sixtyDaysAgo) {
          priorTagCounts.set(tag, (priorTagCounts.get(tag) || 0) + 1);
        }
      });

      // Co-occurrence
      if (tags.length >= 2) {
        for (let i = 0; i < tags.length; i++) {
          for (let j = i + 1; j < tags.length; j++) {
            const [t1, t2] = tags[i] < tags[j] ? [tags[i], tags[j]] : [tags[j], tags[i]];
            if (!cooccurrence.has(t1)) cooccurrence.set(t1, new Map());
            cooccurrence.get(t1)!.set(t2, (cooccurrence.get(t1)!.get(t2) || 0) + 1);
          }
        }
      }
    });

    // Sort all tags by count
    const allTags = Array.from(tagCounts.entries())
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count);

    // ==================== SUMMARY STATS ====================
    const memoriesThisMonth = memories.filter((m) => new Date(m.created_at) >= startOfMonth).length;

    // Count by day of week
    const dayOfWeekCounts = [0, 0, 0, 0, 0, 0, 0];
    const hourCounts = Array(24).fill(0);
    const dailyCounts = new Map<string, number>();

    memories.forEach((m) => {
      const date = new Date(m.created_at);
      dayOfWeekCounts[date.getDay()]++;
      hourCounts[date.getHours()]++;

      const dateStr = m.created_at.split('T')[0];
      dailyCounts.set(dateStr, (dailyCounts.get(dateStr) || 0) + 1);
    });

    // Most active day of week
    const maxDayIdx = dayOfWeekCounts.indexOf(Math.max(...dayOfWeekCounts));
    const mostActiveDay = DAY_NAMES[maxDayIdx];

    // Streak
    const currentStreak = calculateStreak(memories);

    // Average memories per day (last 30 days)
    const recentMemories = memories.filter((m) => new Date(m.created_at) >= thirtyDaysAgo);
    const avgMemoriesPerDay = Math.round((recentMemories.length / 30) * 10) / 10;

    // Find surprising connection (cross-category co-occurrence)
    let surprisingConnection: { tag1: string; tag2: string; count: number } | undefined;
    let maxCrossCount = 0;

    cooccurrence.forEach((innerMap, tag1) => {
      const cat1 = categorizeTag(tag1);
      innerMap.forEach((count, tag2) => {
        const cat2 = categorizeTag(tag2);
        // Cross-category and significant count
        if (cat1 && cat2 && cat1 !== cat2 && count > maxCrossCount && count >= 5) {
          maxCrossCount = count;
          surprisingConnection = { tag1, tag2, count };
        }
      });
    });

    const summary: SummaryStats = {
      totalMemories: memories.length,
      memoriesThisMonth,
      topTags: allTags.slice(0, 3),
      mostActiveDay,
      currentStreak,
      avgMemoriesPerDay,
      surprisingConnection,
    };

    // ==================== LIFE BALANCE ====================
    const categoryMemoryCounts: Record<LifeCategory, number> = {
      work: 0,
      family: 0,
      health: 0,
      learning: 0,
      social: 0,
      hobbies: 0,
    };

    // Count memories per category (a memory can count for multiple categories)
    memories.forEach((memory) => {
      const tags = memory.tags || [];
      const categoriesHit = new Set<LifeCategory>();

      tags.forEach((tag) => {
        const category = categorizeTag(tag);
        if (category) categoriesHit.add(category);
      });

      categoriesHit.forEach((cat) => {
        categoryMemoryCounts[cat]++;
      });
    });

    const maxCategoryCount = Math.max(...Object.values(categoryMemoryCounts), 1);

    const lifeBalance: LifeBalanceData[] = (Object.keys(LIFE_CATEGORIES) as LifeCategory[]).map((category) => ({
      category,
      label: category.charAt(0).toUpperCase() + category.slice(1),
      value: Math.round((categoryMemoryCounts[category] / maxCategoryCount) * 100),
      rawCount: categoryMemoryCounts[category],
      color: CATEGORY_COLORS[category],
    }));

    // ==================== TRENDING ====================
    const allTagsForTrending = new Set([...recentTagCounts.keys(), ...priorTagCounts.keys()]);
    const trendingData: TrendingTag[] = [];

    allTagsForTrending.forEach((tag) => {
      const recentCount = recentTagCounts.get(tag) || 0;
      const priorCount = priorTagCounts.get(tag) || 0;

      // Calculate percentage change
      let change = 0;
      if (priorCount === 0 && recentCount > 0) {
        change = 100; // New tag
      } else if (priorCount > 0) {
        change = Math.round(((recentCount - priorCount) / priorCount) * 100);
      }

      // Days since last mention
      const lastSeen = tagLastSeen.get(tag);
      const daysSinceLastMention = lastSeen
        ? Math.floor((now.getTime() - lastSeen.getTime()) / (1000 * 60 * 60 * 24))
        : undefined;

      trendingData.push({
        tag,
        recentCount,
        priorCount,
        change,
        daysSinceLastMention,
      });
    });

    // Rising: positive change, has recent activity
    const risingTags = trendingData
      .filter((t) => t.change > 20 && t.recentCount >= 3)
      .sort((a, b) => b.change - a.change)
      .slice(0, 5);

    // Fading: negative change or not mentioned recently
    const fadingTags = trendingData
      .filter((t) => {
        // Either declining significantly or hasn't been mentioned in 14+ days but was active before
        return (t.change < -30 && t.priorCount >= 3) || (t.daysSinceLastMention && t.daysSinceLastMention >= 14 && t.priorCount >= 3);
      })
      .sort((a, b) => a.change - b.change)
      .slice(0, 5);

    // ==================== ACTIVITY CALENDAR ====================
    // Generate last 365 days
    const activityCalendar: ActivityDay[] = [];
    const startDate = new Date(now);
    startDate.setDate(startDate.getDate() - 364);
    startDate.setHours(0, 0, 0, 0);

    // Find the Sunday of the week containing startDate
    const firstSunday = new Date(startDate);
    firstSunday.setDate(firstSunday.getDate() - firstSunday.getDay());

    let weekNumber = 0;
    for (let d = new Date(firstSunday); d <= now; d.setDate(d.getDate() + 1)) {
      const dateStr = d.toISOString().split('T')[0];
      const dayOfWeek = d.getDay();

      if (dayOfWeek === 0 && activityCalendar.length > 0) {
        weekNumber++;
      }

      activityCalendar.push({
        date: dateStr,
        count: dailyCounts.get(dateStr) || 0,
        dayOfWeek,
        weekNumber,
      });
    }

    // ==================== TIME PATTERNS ====================
    const totalDayCount = dayOfWeekCounts.reduce((a, b) => a + b, 0);
    const dayOfWeekPattern: TimePattern[] = DAY_NAMES.map((name, idx) => ({
      label: name,
      count: dayOfWeekCounts[idx],
      percentage: totalDayCount > 0 ? Math.round((dayOfWeekCounts[idx] / totalDayCount) * 100) : 0,
    }));

    // Group hours into time periods
    const hourPeriods = [
      { label: 'Morning', hours: [6, 7, 8, 9, 10, 11] },
      { label: 'Afternoon', hours: [12, 13, 14, 15, 16, 17] },
      { label: 'Evening', hours: [18, 19, 20, 21] },
      { label: 'Night', hours: [22, 23, 0, 1, 2, 3, 4, 5] },
    ];

    const totalHourCount = hourCounts.reduce((a: number, b: number) => a + b, 0);
    const hourPattern: TimePattern[] = hourPeriods.map((period) => {
      const count = period.hours.reduce((sum, h) => sum + hourCounts[h], 0);
      return {
        label: period.label,
        count,
        percentage: totalHourCount > 0 ? Math.round((count / totalHourCount) * 100) : 0,
      };
    });

    return {
      summary,
      lifeBalance,
      risingTags,
      fadingTags,
      activityCalendar,
      dayOfWeekPattern,
      hourPattern,
      allTags,
    };
  }, [memories]);
}
