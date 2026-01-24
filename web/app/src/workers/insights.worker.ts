// Web Worker for computing memory insights off the main thread
// This prevents blocking the UI during expensive computations

import type { Memory } from '@/types/conversation';

// Life balance categories with keywords for auto-categorization
const LIFE_CATEGORIES = {
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

type LifeCategory = keyof typeof LIFE_CATEGORIES;

// Category colors
const CATEGORY_COLORS: Record<LifeCategory, string> = {
  work: '#8B5CF6', // Purple
  family: '#EC4899', // Pink
  health: '#10B981', // Green
  learning: '#3B82F6', // Blue
  social: '#F59E0B', // Amber
  hobbies: '#06B6D4', // Cyan
};

// Helper: Get day of week name
const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

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

// Main computation function
function computeInsights(memories: Memory[]) {
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

  // ==================== 1. TAG COMPUTATION (BASE DATA) ====================
  const tagCounts = new Map<string, number>();
  const tagLastSeen = new Map<string, Date>();
  const recentTagCounts = new Map<string, number>();
  const priorTagCounts = new Map<string, number>();
  const cooccurrence = new Map<string, Map<string, number>>();

  for (const memory of memories) {
    const memoryDate = new Date(memory.created_at);
    const tags = memory.tags || [];

    for (const tag of tags) {
      // Overall counts
      tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);

      // Last seen
      if (!tagLastSeen.has(tag) || memoryDate > tagLastSeen.get(tag)!) {
        tagLastSeen.set(tag, memoryDate);
      }

      // Recent vs Prior (for trending)
      if (memoryDate >= thirtyDaysAgo) {
        recentTagCounts.set(tag, (recentTagCounts.get(tag) || 0) + 1);
      } else if (memoryDate >= sixtyDaysAgo) {
        priorTagCounts.set(tag, (priorTagCounts.get(tag) || 0) + 1);
      }

      // Co-occurrence
      for (const otherTag of tags) {
        if (tag !== otherTag) {
          if (!cooccurrence.has(tag)) {
            cooccurrence.set(tag, new Map());
          }
          const tagCooccur = cooccurrence.get(tag)!;
          tagCooccur.set(otherTag, (tagCooccur.get(otherTag) || 0) + 1);
        }
      }
    }
  }

  // ==================== 2. DATE-BASED METRICS ====================
  const dateMetrics = (() => {
    const dailyCounts = new Map<string, number>();
    const dayOfWeekCounts = new Array(7).fill(0);
    const hourCounts = new Array(24).fill(0);
    const thisMonthCount = memories.filter(
      (m) => new Date(m.created_at).getMonth() === now.getMonth() && new Date(m.created_at).getFullYear() === now.getFullYear()
    ).length;

    for (const memory of memories) {
      const date = new Date(memory.created_at);
      const dateStr = date.toISOString().split('T')[0];
      dailyCounts.set(dateStr, (dailyCounts.get(dateStr) || 0) + 1);

      const dayOfWeek = date.getDay();
      dayOfWeekCounts[dayOfWeek]++;

      const hour = date.getHours();
      hourCounts[hour]++;
    }

    // Find most active day
    let mostActiveDay = '';
    let maxCount = 0;
    for (const [date, count] of dailyCounts.entries()) {
      if (count > maxCount) {
        maxCount = count;
        mostActiveDay = date;
      }
    }

    const totalDays = Math.max(
      1,
      Math.ceil((now.getTime() - new Date(memories[memories.length - 1]?.created_at || now).getTime()) / (1000 * 60 * 60 * 24))
    );
    const avgMemoriesPerDay = memories.length / totalDays;

    return {
      dailyCounts,
      dayOfWeekCounts,
      hourCounts,
      thisMonthCount,
      mostActiveDay,
      avgMemoriesPerDay,
    };
  })();

  // ==================== 3. ALL TAGS ====================
  const allTags = Array.from(tagCounts.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);

  // ==================== 4. SUMMARY STATS ====================
  const topTags = allTags.slice(0, 5);
  const currentStreak = calculateStreak(memories);

  // Find surprising connection
  let surprisingConnection: { tag1: string; tag2: string; count: number } | undefined;
  let maxCooccur = 0;
  for (const [tag1, relatedTags] of cooccurrence.entries()) {
    for (const [tag2, count] of relatedTags.entries()) {
      if (count > maxCooccur && count >= 3) {
        maxCooccur = count;
        surprisingConnection = { tag1, tag2, count };
      }
    }
  }

  const summary = {
    totalMemories: memories.length,
    memoriesThisMonth: dateMetrics.thisMonthCount,
    topTags,
    mostActiveDay: dateMetrics.mostActiveDay,
    currentStreak,
    avgMemoriesPerDay: Math.round(dateMetrics.avgMemoriesPerDay * 10) / 10,
    surprisingConnection,
  };

  // ==================== 5. LIFE BALANCE ====================
  const categoryCounts = new Map<LifeCategory, number>();

  for (const tag of tagCounts.keys()) {
    const category = categorizeTag(tag);
    if (category) {
      const count = tagCounts.get(tag) || 0;
      categoryCounts.set(category, (categoryCounts.get(category) || 0) + count);
    }
  }

  const totalCategorized = Array.from(categoryCounts.values()).reduce((sum, count) => sum + count, 0);
  const lifeBalance = (Object.keys(CATEGORY_COLORS) as LifeCategory[])
    .map((category) => {
      const rawCount = categoryCounts.get(category) || 0;
      const value = totalCategorized > 0 ? Math.round((rawCount / totalCategorized) * 100) : 0;
      return {
        category,
        label: category.charAt(0).toUpperCase() + category.slice(1),
        value,
        rawCount,
        color: CATEGORY_COLORS[category],
      };
    })
    .sort((a, b) => b.value - a.value);

  // ==================== 6. TRENDING TAGS (RISING & FADING) ====================
  const trendingData: Array<{
    tag: string;
    recentCount: number;
    priorCount: number;
    change: number;
    daysSinceLastMention?: number;
  }> = [];

  for (const [tag, recentCount] of recentTagCounts.entries()) {
    const priorCount = priorTagCounts.get(tag) || 0;
    const totalCount = tagCounts.get(tag) || 0;

    // Only consider tags with meaningful data
    if (totalCount >= 3 && (recentCount > 0 || priorCount > 0)) {
      const change = priorCount > 0 ? ((recentCount - priorCount) / priorCount) * 100 : recentCount > 0 ? 100 : 0;

      const lastSeen = tagLastSeen.get(tag);
      const daysSinceLastMention = lastSeen ? Math.floor((now.getTime() - lastSeen.getTime()) / (1000 * 60 * 60 * 24)) : undefined;

      trendingData.push({
        tag,
        recentCount,
        priorCount,
        change,
        daysSinceLastMention,
      });
    }
  }

  const risingTags = trendingData
    .filter((t) => t.change > 0 && t.recentCount >= 2)
    .sort((a, b) => b.change - a.change)
    .slice(0, 5);

  const fadingTags = trendingData
    .filter((t) => t.change < 0 && t.priorCount >= 2)
    .sort((a, b) => a.change - b.change)
    .slice(0, 5);

  // ==================== 7. ACTIVITY CALENDAR ====================
  const activityCalendar = (() => {
    const last90Days = new Date(now);
    last90Days.setDate(last90Days.getDate() - 90);

    const calendar: Array<{
      date: string;
      count: number;
      dayOfWeek: number;
      weekNumber: number;
    }> = [];

    for (let i = 90; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split('T')[0];
      const count = dateMetrics.dailyCounts.get(dateStr) || 0;

      calendar.push({
        date: dateStr,
        count,
        dayOfWeek: date.getDay(),
        weekNumber: Math.floor((90 - i) / 7),
      });
    }

    return calendar;
  })();

  // ==================== 8. TIME PATTERNS ====================
  const dayOfWeekPattern = DAY_NAMES.map((label, i) => {
    const count = dateMetrics.dayOfWeekCounts[i];
    const percentage = memories.length > 0 ? Math.round((count / memories.length) * 100) : 0;
    return { label, count, percentage };
  });

  const hourPattern = Array.from({ length: 24 }, (_, hour) => {
    const count = dateMetrics.hourCounts[hour];
    const percentage = memories.length > 0 ? Math.round((count / memories.length) * 100) : 0;
    const label = `${hour.toString().padStart(2, '0')}:00`;
    return { label, count, percentage };
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
}

// Worker message handler
self.onmessage = (e: MessageEvent) => {
  const { type, memories } = e.data;

  if (type === 'compute') {
    try {
      const insights = computeInsights(memories);
      self.postMessage({ type: 'result', insights });
    } catch (error) {
      self.postMessage({ type: 'error', error: error instanceof Error ? error.message : 'Unknown error' });
    }
  }
};

// For TypeScript
export {};
