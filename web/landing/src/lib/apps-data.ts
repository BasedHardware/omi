export interface App {
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  ratingAvg: number;
  ratingCount: number;
  capabilities: string[];
  createdAt: string;
}

export interface CategoryMeta {
  slug: string;
  name: string;
  iconName: string;
  color: string;
  accent: string;
}

export const categories: CategoryMeta[] = [
  { slug: 'productivity', name: 'Productivity', iconName: 'Briefcase', color: 'text-indigo-400', accent: 'bg-indigo-500/10' },
  { slug: 'conversation', name: 'Conversation Insights', iconName: 'MessageSquare', color: 'text-violet-400', accent: 'bg-violet-500/10' },
  { slug: 'education', name: 'Education & Learning', iconName: 'GraduationCap', color: 'text-blue-400', accent: 'bg-blue-500/10' },
  { slug: 'persona', name: 'Persona & AI Chat', iconName: 'Brain', color: 'text-fuchsia-400', accent: 'bg-fuchsia-500/10' },
  { slug: 'utilities', name: 'Utilities & Tools', iconName: 'Wrench', color: 'text-sky-400', accent: 'bg-sky-500/10' },
  { slug: 'health', name: 'Health & Fitness', iconName: 'Heart', color: 'text-rose-400', accent: 'bg-rose-500/10' },
  { slug: 'integration', name: 'Integrations', iconName: 'Globe', color: 'text-cyan-400', accent: 'bg-cyan-500/10' },
  { slug: 'entertainment', name: 'Entertainment', iconName: 'Gamepad2', color: 'text-orange-400', accent: 'bg-orange-500/10' },
];

// Mock apps — replace with API call later
export const mockApps: App[] = [
  {
    id: 'slack-sync',
    name: 'Slack Sync',
    description: 'Automatically post meeting summaries and action items to your Slack channels.',
    author: 'Nooto Team',
    image: '',
    category: 'integration',
    installs: 45200,
    ratingAvg: 4.7,
    ratingCount: 312,
    capabilities: ['memory_trigger', 'external_integration'],
    createdAt: '2026-01-15',
  },
  {
    id: 'notion-notes',
    name: 'Notion Notes',
    description: 'Sync conversation transcripts and summaries directly to your Notion workspace.',
    author: 'Nooto Team',
    image: '',
    category: 'integration',
    installs: 38100,
    ratingAvg: 4.6,
    ratingCount: 287,
    capabilities: ['memory_trigger', 'external_integration'],
    createdAt: '2026-01-20',
  },
  {
    id: 'meeting-coach',
    name: 'Meeting Coach',
    description: 'Get real-time feedback on your speaking habits, filler words, and engagement.',
    author: 'AI Labs',
    image: '',
    category: 'productivity',
    installs: 32400,
    ratingAvg: 4.5,
    ratingCount: 198,
    capabilities: ['real_time_transcript'],
    createdAt: '2026-02-01',
  },
  {
    id: 'action-tracker',
    name: 'Action Tracker',
    description: 'Automatically extract and track action items across all your conversations.',
    author: 'Nooto Team',
    image: '',
    category: 'productivity',
    installs: 29800,
    ratingAvg: 4.8,
    ratingCount: 245,
    capabilities: ['memory_trigger'],
    createdAt: '2026-01-10',
  },
  {
    id: 'daily-digest',
    name: 'Daily Digest',
    description: 'Receive a beautifully formatted daily summary of all your conversations.',
    author: 'Nooto Team',
    image: '',
    category: 'productivity',
    installs: 27500,
    ratingAvg: 4.4,
    ratingCount: 176,
    capabilities: ['memory_trigger'],
    createdAt: '2026-02-10',
  },
  {
    id: 'language-tutor',
    name: 'Language Tutor',
    description: 'Practice conversations in 15+ languages with real-time pronunciation feedback.',
    author: 'LingvoAI',
    image: '',
    category: 'education',
    installs: 22100,
    ratingAvg: 4.3,
    ratingCount: 156,
    capabilities: ['real_time_transcript', 'chat_tool'],
    createdAt: '2026-02-15',
  },
  {
    id: 'fitness-coach',
    name: 'Fitness Coach',
    description: 'AI fitness advisor that tracks your health discussions and provides personalized tips.',
    author: 'HealthTech',
    image: '',
    category: 'health',
    installs: 18700,
    ratingAvg: 4.2,
    ratingCount: 134,
    capabilities: ['chat_prompt'],
    createdAt: '2026-02-20',
  },
  {
    id: 'zapier-connect',
    name: 'Zapier Connect',
    description: 'Connect Nooto to 5000+ apps through Zapier automations.',
    author: 'Nooto Team',
    image: '',
    category: 'integration',
    installs: 41300,
    ratingAvg: 4.5,
    ratingCount: 267,
    capabilities: ['memory_trigger', 'external_integration'],
    createdAt: '2026-01-05',
  },
  {
    id: 'sales-assistant',
    name: 'Sales Assistant',
    description: 'CRM integration that logs calls, extracts leads, and updates deal stages automatically.',
    author: 'SalesForce Labs',
    image: '',
    category: 'productivity',
    installs: 15200,
    ratingAvg: 4.6,
    ratingCount: 98,
    capabilities: ['memory_trigger', 'external_integration'],
    createdAt: '2026-03-01',
  },
  {
    id: 'therapy-companion',
    name: 'Therapy Companion',
    description: 'Reflective AI companion for journaling, self-awareness, and mental wellness.',
    author: 'MindfulAI',
    image: '',
    category: 'health',
    installs: 14300,
    ratingAvg: 4.7,
    ratingCount: 112,
    capabilities: ['chat_prompt', 'memory_trigger'],
    createdAt: '2026-02-25',
  },
  {
    id: 'code-reviewer',
    name: 'Code Reviewer',
    description: 'Discuss code out loud and get instant review feedback, suggestions, and documentation.',
    author: 'DevTools Inc',
    image: '',
    category: 'utilities',
    installs: 12800,
    ratingAvg: 4.4,
    ratingCount: 89,
    capabilities: ['chat_tool', 'real_time_transcript'],
    createdAt: '2026-03-05',
  },
  {
    id: 'linear-sync',
    name: 'Linear Sync',
    description: 'Create Linear issues from conversation action items and track project progress.',
    author: 'Nooto Team',
    image: '',
    category: 'integration',
    installs: 11500,
    ratingAvg: 4.5,
    ratingCount: 76,
    capabilities: ['memory_trigger', 'external_integration'],
    createdAt: '2026-03-10',
  },
  {
    id: 'debate-partner',
    name: 'Debate Partner',
    description: 'Sharpen your arguments with an AI that challenges your thinking from multiple perspectives.',
    author: 'ThinkTank AI',
    image: '',
    category: 'persona',
    installs: 9800,
    ratingAvg: 4.3,
    ratingCount: 67,
    capabilities: ['chat_prompt'],
    createdAt: '2026-03-12',
  },
  {
    id: 'trivia-master',
    name: 'Trivia Master',
    description: 'Play voice-based trivia games with friends. Thousands of questions across 20+ topics.',
    author: 'FunApps',
    image: '',
    category: 'entertainment',
    installs: 8400,
    ratingAvg: 4.1,
    ratingCount: 54,
    capabilities: ['chat_tool'],
    createdAt: '2026-03-15',
  },
  {
    id: 'study-buddy',
    name: 'Study Buddy',
    description: 'Record lectures and automatically generate flashcards, quizzes, and study guides.',
    author: 'EduTech',
    image: '',
    category: 'education',
    installs: 16900,
    ratingAvg: 4.6,
    ratingCount: 143,
    capabilities: ['memory_trigger'],
    createdAt: '2026-02-08',
  },
  {
    id: 'github-issues',
    name: 'GitHub Issues',
    description: 'Create GitHub issues directly from your conversations. Just say what needs to be done.',
    author: 'DevTools Inc',
    image: '',
    category: 'integration',
    installs: 10200,
    ratingAvg: 4.4,
    ratingCount: 72,
    capabilities: ['chat_tool', 'external_integration'],
    createdAt: '2026-03-08',
  },
];

export function formatInstalls(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
}

export function getAppsByCategory(cat: string): App[] {
  return mockApps.filter((a) => a.category === cat).sort((a, b) => b.installs - a.installs);
}

export function getFeaturedApps(): App[] {
  return [...mockApps].sort((a, b) => b.installs - a.installs).slice(0, 3);
}

export function getPopularApps(): App[] {
  return [...mockApps].sort((a, b) => b.installs - a.installs).slice(0, 9);
}

export function getAppById(id: string): App | undefined {
  return mockApps.find((a) => a.id === id);
}

export function getCategoryBySlug(slug: string): CategoryMeta | undefined {
  return categories.find((c) => c.slug === slug);
}
