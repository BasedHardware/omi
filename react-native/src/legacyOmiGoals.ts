import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_GOALS = 4;

class GoalError extends Error {
  constructor() {
    super('Omi goals are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new GoalError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new GoalError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new GoalError();
  }
  return value;
}

function goalMetric(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
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

function goalRawNum(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function parseOmiGoals(body: string): OmiGoal[] {
  const rows = array(JSON.parse(body), 32);
  const items: OmiGoal[] = [];
  const seen = new Set<string>();
  for (const raw of rows) {
    if (items.length === MAX_GOALS) {
      break;
    }
    const row = object(raw);
    const id = visibleDisplayText(text(row.id, 256));
    if (id === '') {
      throw new GoalError();
    }
    if (seen.has(id)) {
      throw new GoalError();
    }
    seen.add(id);
    const title = visibleDisplayText(text(row.title, 10000));
    if (title === '') {
      continue;
    }
    const current = goalMetric(row.current_value);
    const target = goalMetric(row.target_value);
    if (current === null || target === null) {
      continue;
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
