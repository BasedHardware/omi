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

export const getCategoryDisplay = (category: string): string => {
  const categoryMap: Record<string, string> = {
    'social-and-relationships': 'Social & Relationships',
    'utilities-and-tools': 'Utilities & Tools',
    'productivity-and-organization': 'Productivity',
    'conversation-analysis': 'Conversation Insights',
    'education-and-learning': 'Learning & Education',
    financial: 'Finance',
    other: 'General',
    'emotional-and-mental-support': 'Mental Wellness',
    'safety-and-security': 'Security & Safety',
    'health-and-wellness': 'Health & Fitness',
    'personality-emulation': 'Persona & AI Chat',
    'shopping-and-commerce': 'Shopping',
    'news-and-information': 'News & Info',
    'entertainment-and-fun': 'Entertainment & Games',
  };
  return categoryMap[category] ?? category;
};

export const getCategoryIcon = (category: string): LucideIcon => {
  const iconMap: Record<string, LucideIcon> = {
    'productivity-and-organization': Briefcase,
    'conversation-analysis': MessageSquare,
    'education-and-learning': GraduationCap,
    'personality-emulation': Brain,
    'utilities-and-tools': Wrench,
    'health-and-wellness': Heart,
    'safety-and-security': Shield,
    'news-and-information': Newspaper,
    'social-and-relationships': Users,
    financial: DollarSign,
    'entertainment-and-fun': Gamepad2,
    'shopping-and-commerce': ShoppingBag,
    'travel-and-exploration': Globe,
    other: Sparkles,
  };
  return iconMap[category] ?? Sparkles;
};
