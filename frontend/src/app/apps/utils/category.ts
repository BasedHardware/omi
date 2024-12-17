import {
  Briefcase,
  Brain,
  GraduationCap,
  MessageSquare,
  Wrench,
  Heart,
  Shield,
  Newspaper,
  Users,
  DollarSign,
  Gamepad2,
  ShoppingBag,
  Globe,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

export interface CategoryMetadata {
  id: string;
  displayName: string;
  description: string;
  icon: LucideIcon;
  theme: CategoryTheme;
}

export interface CategoryTheme {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
}

export const categoryMetadata: Record<string, CategoryMetadata> = {
  'productivity-and-organization': {
    id: 'productivity-and-organization',
    displayName: 'Productivity',
    description: 'Tools to enhance your productivity and organization',
    icon: Briefcase,
    theme: {
      primary: 'text-indigo-500',
      secondary: 'text-indigo-400',
      accent: 'bg-indigo-500/15',
      background: 'bg-indigo-500/5',
    },
  },
  'conversation-analysis': {
    id: 'conversation-analysis',
    displayName: 'Conversation Insights',
    description: 'Analyze and improve your conversations',
    icon: MessageSquare,
    theme: {
      primary: 'text-violet-500',
      secondary: 'text-violet-400',
      accent: 'bg-violet-500/15',
      background: 'bg-violet-500/5',
    },
  },
  'education-and-learning': {
    id: 'education-and-learning',
    displayName: 'Learning & Education',
    description: 'Enhance your learning experience',
    icon: GraduationCap,
    theme: {
      primary: 'text-blue-500',
      secondary: 'text-blue-400',
      accent: 'bg-blue-500/15',
      background: 'bg-blue-500/5',
    },
  },
  'personality-emulation': {
    id: 'personality-emulation',
    displayName: 'Persona & AI Chat',
    description: 'Interact with AI personalities',
    icon: Brain,
    theme: {
      primary: 'text-fuchsia-500',
      secondary: 'text-fuchsia-400',
      accent: 'bg-fuchsia-500/15',
      background: 'bg-fuchsia-500/5',
    },
  },
  'utilities-and-tools': {
    id: 'utilities-and-tools',
    displayName: 'Utilities & Tools',
    description: 'Useful tools and utilities',
    icon: Wrench,
    theme: {
      primary: 'text-sky-500',
      secondary: 'text-sky-400',
      accent: 'bg-sky-500/15',
      background: 'bg-sky-500/5',
    },
  },
  'health-and-wellness': {
    id: 'health-and-wellness',
    displayName: 'Health & Fitness',
    description: 'Monitor and improve your health',
    icon: Heart,
    theme: {
      primary: 'text-rose-500',
      secondary: 'text-rose-400',
      accent: 'bg-rose-500/15',
      background: 'bg-rose-500/5',
    },
  },
  'safety-and-security': {
    id: 'safety-and-security',
    displayName: 'Security & Safety',
    description: 'Protect and secure your data',
    icon: Shield,
    theme: {
      primary: 'text-emerald-500',
      secondary: 'text-emerald-400',
      accent: 'bg-emerald-500/15',
      background: 'bg-emerald-500/5',
    },
  },
  'news-and-information': {
    id: 'news-and-information',
    displayName: 'News & Info',
    description: 'Stay informed and up-to-date',
    icon: Newspaper,
    theme: {
      primary: 'text-amber-500',
      secondary: 'text-amber-400',
      accent: 'bg-amber-500/15',
      background: 'bg-amber-500/5',
    },
  },
  'social-and-relationships': {
    id: 'social-and-relationships',
    displayName: 'Social & Relationships',
    description: 'Enhance your social interactions',
    icon: Users,
    theme: {
      primary: 'text-pink-500',
      secondary: 'text-pink-400',
      accent: 'bg-pink-500/15',
      background: 'bg-pink-500/5',
    },
  },
  financial: {
    id: 'financial',
    displayName: 'Finance',
    description: 'Manage your finances',
    icon: DollarSign,
    theme: {
      primary: 'text-green-500',
      secondary: 'text-green-400',
      accent: 'bg-green-500/15',
      background: 'bg-green-500/5',
    },
  },
  'entertainment-and-fun': {
    id: 'entertainment-and-fun',
    displayName: 'Entertainment & Games',
    description: 'Have fun and stay entertained',
    icon: Gamepad2,
    theme: {
      primary: 'text-orange-500',
      secondary: 'text-orange-400',
      accent: 'bg-orange-500/15',
      background: 'bg-orange-500/5',
    },
  },
  'shopping-and-commerce': {
    id: 'shopping-and-commerce',
    displayName: 'Shopping',
    description: 'Shop and manage purchases',
    icon: ShoppingBag,
    theme: {
      primary: 'text-teal-500',
      secondary: 'text-teal-400',
      accent: 'bg-teal-500/15',
      background: 'bg-teal-500/5',
    },
  },
  integration: {
    id: 'integration',
    displayName: 'Integration Apps',
    description: 'Connect with external services',
    icon: Globe,
    theme: {
      primary: 'text-cyan-500',
      secondary: 'text-cyan-400',
      accent: 'bg-cyan-500/15',
      background: 'bg-cyan-500/5',
    },
  },
  other: {
    id: 'other',
    displayName: 'General',
    description: 'Other useful applications',
    icon: Sparkles,
    theme: {
      primary: 'text-purple-500',
      secondary: 'text-purple-400',
      accent: 'bg-purple-500/15',
      background: 'bg-purple-500/5',
    },
  },
};

export function getCategoryMetadata(category: string): CategoryMetadata {
  return categoryMetadata[category] || categoryMetadata.other;
}

export function getAdjacentCategories(currentCategory: string): {
  prev?: string;
  next?: string;
} {
  const categories = Object.keys(categoryMetadata);
  const currentIndex = categories.indexOf(currentCategory);

  return {
    prev: currentIndex > 0 ? categories[currentIndex - 1] : undefined,
    next: currentIndex < categories.length - 1 ? categories[currentIndex + 1] : undefined,
  };
}

export const getCategoryDisplay = (category: string): string => {
  return getCategoryMetadata(category).displayName;
};

export const getCategoryIcon = (category: string): LucideIcon => {
  return getCategoryMetadata(category).icon;
};
