import {
  Brain,
  CheckSquare,
  GanttChartSquare,
  House,
  Mic,
  type LucideIcon,
} from 'lucide-react';

/**
 * Single source of truth for primary navigation. Every surface that lists
 * destinations (desktop sidebar rail, mobile bottom bar) renders a subset of
 * this one list, so order, hrefs, and labels line up by construction.
 */
export type NavSurface = 'sidebar' | 'bottom-bar';

export interface NavItemConfig {
  /** Label used by the sidebar. */
  label: string;
  /** Shorter label used by the bottom bar; falls back to `label`. */
  shortLabel?: string;
  href: string;
  icon: LucideIcon;
  /** Which navigation surfaces list this destination. */
  surfaces: NavSurface[];
}

// Order mirrors the desktop rail (`SidebarNavItem.mainItems`): Home, then
// Conversations, Memories, Tasks, then the surfaces web adds on top. Chat has
// no row of its own on either client — it is what Home opens into. Record is
// bottom-bar-only: on desktop it lives behind the macOS floating bar, so the
// rail does not list it.
export const NAV_ITEMS: NavItemConfig[] = [
  {
    label: 'Home',
    href: '/home',
    icon: House,
    surfaces: ['sidebar', 'bottom-bar'],
  },
  {
    label: 'Conversations',
    href: '/conversations',
    icon: GanttChartSquare,
    surfaces: ['sidebar', 'bottom-bar'],
  },
  {
    label: 'Memories',
    href: '/memories',
    icon: Brain,
    surfaces: ['sidebar'],
  },
  {
    label: 'Record',
    href: '/record',
    icon: Mic,
    surfaces: ['bottom-bar'],
  },
  {
    label: 'Tasks',
    href: '/tasks',
    icon: CheckSquare,
    surfaces: ['sidebar', 'bottom-bar'],
  },
];

export function navItemsFor(surface: NavSurface): NavItemConfig[] {
  return NAV_ITEMS.filter((item) => item.surfaces.includes(surface));
}
