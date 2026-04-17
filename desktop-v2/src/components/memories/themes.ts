import {
  Briefcase,
  Users,
  HeartPulse,
  Palette,
  Repeat,
  ThumbsUp,
  Target,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export type ThemeKey =
  | "work"
  | "people"
  | "health"
  | "interests"
  | "habits"
  | "preferences"
  | "plans"
  | "other";

export type ThemeDef = {
  key: ThemeKey;
  label: string;
  icon: LucideIcon;
};

export const THEMES: readonly ThemeDef[] = [
  { key: "work", label: "Work & career", icon: Briefcase },
  { key: "people", label: "People & relationships", icon: Users },
  { key: "health", label: "Health & body", icon: HeartPulse },
  { key: "interests", label: "Interests & hobbies", icon: Palette },
  { key: "habits", label: "Habits & routines", icon: Repeat },
  { key: "preferences", label: "Preferences & tastes", icon: ThumbsUp },
  { key: "plans", label: "Plans & goals", icon: Target },
  { key: "other", label: "Other", icon: Sparkles },
] as const;

export const THEME_MAP: Record<ThemeKey, ThemeDef> = THEMES.reduce(
  (acc, t) => {
    acc[t.key] = t;
    return acc;
  },
  {} as Record<ThemeKey, ThemeDef>,
);
