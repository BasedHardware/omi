import type {DesktopRoute} from './DesktopTopChrome';

// First-run exploration checklist. Each item completes the first time the
// user actually arrives at the surface it points at, and progress persists
// through the exploreProgress desktop preference (CSV of check ids).
export type ExploreCheck =
  | 'recall'
  | 'chat'
  | 'conversations'
  | 'tasks'
  | 'settings';

export type ExploreChecklistItem = {
  id: ExploreCheck;
  label: string;
  route: DesktopRoute;
};

export const EXPLORE_CHECKLIST: ExploreChecklistItem[] = [
  {id: 'recall', label: 'Find something you saw', route: 'Rewind'},
  {id: 'chat', label: 'Ask about your day', route: 'Chat'},
  {
    id: 'conversations',
    label: 'Browse your conversations',
    route: 'Conversations',
  },
  {id: 'tasks', label: 'Check your tasks', route: 'Tasks'},
  {id: 'settings', label: 'Make Omi yours', route: 'Settings'},
];

const VALID_IDS = new Set<string>(EXPLORE_CHECKLIST.map(item => item.id));

export function exploreCheckForRoute(route: DesktopRoute): ExploreCheck | null {
  return EXPLORE_CHECKLIST.find(item => item.route === route)?.id ?? null;
}

export function parseExploreProgress(value: unknown): Set<ExploreCheck> {
  const done = new Set<ExploreCheck>();
  if (typeof value !== 'string') {
    return done;
  }
  for (const part of value.split(',')) {
    const id = part.trim();
    if (VALID_IDS.has(id)) {
      done.add(id as ExploreCheck);
    }
  }
  return done;
}

export function serializeExploreProgress(done: Set<ExploreCheck>): string {
  return EXPLORE_CHECKLIST.filter(item => done.has(item.id))
    .map(item => item.id)
    .join(',');
}
