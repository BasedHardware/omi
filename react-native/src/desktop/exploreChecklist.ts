// First-run exploration checklist. Each item completes the first time the
// user actually arrives at the surface it points at, and progress persists
// through the exploreProgress desktop preference (CSV of check ids). Each
// interface version maps check ids to its own destinations: v5.1 targets the
// Activity filter chips, v5 targets the pages rail.
export type ExploreCheck =
  | 'recall'
  | 'chat'
  | 'conversations'
  | 'tasks'
  | 'settings';

export type ExploreChecklistItem = {
  id: ExploreCheck;
  label: string;
};

export const EXPLORE_CHECKLIST: ExploreChecklistItem[] = [
  {id: 'recall', label: 'Find something you saw'},
  {id: 'chat', label: 'Ask about your day'},
  {id: 'conversations', label: 'Browse your conversations'},
  {id: 'tasks', label: 'Check your tasks'},
  {id: 'settings', label: 'Make Omi yours'},
];

const VALID_IDS = new Set<string>(EXPLORE_CHECKLIST.map(item => item.id));

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
