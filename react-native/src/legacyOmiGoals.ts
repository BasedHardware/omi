import type {OmiBackend} from './omiNativeTypes';

class GoalError extends Error {
  constructor() {
    super('Omi goals are malformed');
  }
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new GoalError();
  }
  return value;
}

function goalMetric(value: unknown): number | null {
  if (value === undefined || value === null) {
    return 0;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function goalId(value: unknown): string | null {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'string') {
    return text(value, 1_000_000);
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

export type OmiGoal = {
  id: string;
  title: string;
  current: number;
  target: number;
};

export function goalProgressCopy(current: number, target: number): string {
  return `${goalRawNum(current)}/${goalRawNum(target)}`;
}

export function goalTasksProgressCopy(current: number, target: number): string {
  return `(${Math.trunc(current)}/${Math.trunc(target)})`;
}

export function goalTasksTitleCopy(
  title: string,
  current: number,
  target: number,
): string {
  return `${title} ${goalTasksProgressCopy(current, target)}`;
}

function goalRawNum(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function parseOmiGoals(body: string): OmiGoal[] {
  const parsed: unknown = JSON.parse(body);
  if (!Array.isArray(parsed)) {
    throw new GoalError();
  }
  const items: OmiGoal[] = [];
  const seen = new Set<string>();
  for (const raw of parsed) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
      continue;
    }
    const row = raw as Record<string, unknown>;
    const id = goalId(row.id);
    if (id === null) {
      continue;
    }
    if (
      row.title !== undefined &&
      row.title !== null &&
      typeof row.title !== 'string'
    ) {
      continue;
    }
    const title = text(
      typeof row.title === 'string' ? row.title : '',
      1_000_000,
    );
    const current = goalMetric(row.current_value);
    const target = goalMetric(row.target_value);
    if (current === null || target === null) {
      continue;
    }
    if (id !== '') {
      if (seen.has(id)) {
        throw new GoalError();
      }
      seen.add(id);
    }
    items.push({
      id,
      title,
      current,
      target,
    });
  }
  return items;
}

export async function loadOmiGoals(backend: OmiBackend): Promise<OmiGoal[]> {
  const response = await backend.request({
    id: 'omi-goals',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/goals/all',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiGoals(response.body);
  } catch {
    return [];
  }
}
