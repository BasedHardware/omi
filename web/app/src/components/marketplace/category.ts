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
import { t } from '@/lib/i18n';

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
    get displayName() {
      return t('Productivity');
    },
    get description() {
      return t('Tools to enhance your productivity and organization');
    },
    icon: Briefcase,
    theme: {
      primary: 'text-amber-500',
      secondary: 'text-amber-400',
      accent: 'bg-amber-500/15',
      background: 'bg-amber-500/5',
    },
  },
  'conversation-analysis': {
    id: 'conversation-analysis',
    get displayName() {
      return t('Conversation Insights');
    },
    get description() {
      return t('Analyze and improve your conversations');
    },
    icon: MessageSquare,
    theme: {
      primary: 'text-teal-500',
      secondary: 'text-teal-400',
      accent: 'bg-teal-500/15',
      background: 'bg-teal-500/5',
    },
  },
  'education-and-learning': {
    id: 'education-and-learning',
    get displayName() {
      return t('Learning & Education');
    },
    get description() {
      return t('Enhance your learning experience');
    },
    icon: GraduationCap,
    theme: {
      primary: 'text-blue-500',
      secondary: 'text-blue-400',
      accent: 'bg-blue-500/15',
      background: 'bg-blue-500/5',
    },
  },
  'utilities-and-tools': {
    id: 'utilities-and-tools',
    get displayName() {
      return t('Utilities & Tools');
    },
    get description() {
      return t('Useful tools and utilities');
    },
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
    get displayName() {
      return t('Health & Fitness');
    },
    get description() {
      return t('Monitor and improve your health');
    },
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
    get displayName() {
      return t('Security & Safety');
    },
    get description() {
      return t('Protect and secure your data');
    },
    icon: Shield,
    theme: {
      primary: 'text-emerald-500',
      secondary: 'text-emerald-400',
      accent: 'bg-emerald-500/15',
      background: 'bg-emerald-500/5',
    },
  },
  'social-and-relationships': {
    id: 'social-and-relationships',
    get displayName() {
      return t('Social & Relationships');
    },
    get description() {
      return t('Enhance your social interactions');
    },
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
    get displayName() {
      return t('Finance');
    },
    get description() {
      return t('Manage your finances');
    },
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
    get displayName() {
      return t('Entertainment & Games');
    },
    get description() {
      return t('Have fun and stay entertained');
    },
    icon: Gamepad2,
    theme: {
      primary: 'text-orange-500',
      secondary: 'text-orange-400',
      accent: 'bg-orange-500/15',
      background: 'bg-orange-500/5',
    },
  },
  'communication-improvement': {
    id: 'communication-improvement',
    get displayName() {
      return t('Communication');
    },
    get description() {
      return t('Improve your communication skills');
    },
    icon: MessageSquare,
    theme: {
      primary: 'text-cyan-500',
      secondary: 'text-cyan-400',
      accent: 'bg-cyan-500/15',
      background: 'bg-cyan-500/5',
    },
  },
  'emotional-and-mental-support': {
    id: 'emotional-and-mental-support',
    get displayName() {
      return t('Mental Wellness');
    },
    get description() {
      return t('Support for emotional and mental health');
    },
    icon: Heart,
    theme: {
      primary: 'text-text-primary',
      secondary: 'text-text-secondary',
      accent: 'bg-white/[0.08]',
      background: 'bg-white/[0.08]',
    },
  },
  integration: {
    id: 'integration',
    get displayName() {
      return t('Integration Apps');
    },
    get description() {
      return t('Connect with external services');
    },
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
    get displayName() {
      return t('General');
    },
    get description() {
      return t('Other useful applications');
    },
    icon: Sparkles,
    theme: {
      primary: 'text-text-primary',
      secondary: 'text-text-secondary',
      accent: 'bg-white/[0.08]',
      background: 'bg-white/[0.08]',
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
