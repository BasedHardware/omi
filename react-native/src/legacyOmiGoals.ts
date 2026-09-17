import {visibleDisplayText} from './desktopReadClient';
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
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      return null;
    }
    const parsed = Number(value);
    if (value === '' || !Number.isFinite(parsed)) {
      return null;
    }
    return parsed;
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

function paddedKnown(value: unknown): boolean {
  return typeof value === 'string' && visibleDisplayText(value) !== value;
}

function skipPaddedExtras(row: Record<string, unknown>): boolean {
  if (
    paddedKnown(row.created_at) ||
    paddedKnown(row.updated_at) ||
    paddedKnown(row.max_value) ||
    paddedKnown(row.min_value) ||
    paddedKnown(row.focus_rank) ||
    paddedKnown(row.latest_progress_sequence) ||
    paddedKnown(row.ended_at) ||
    paddedKnown(row.horizon_at)
  ) {
    return true;
  }
  if (
    row.metric === null ||
    typeof row.metric !== 'object' ||
    Array.isArray(row.metric)
  ) {
    return false;
  }
  const metric = row.metric as Record<string, unknown>;
  return (
    paddedKnown(metric.current) ||
    paddedKnown(metric.target) ||
    paddedKnown(metric.max) ||
    paddedKnown(metric.min)
  );
}

function presentNullableString(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  text(value, 1_000_000);
}

function presentUnusedStringListItems(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    return;
  }
  for (const item of value) {
    text(item, 1_000_000);
  }
}

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new GoalError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new GoalError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new GoalError();
  }
}

function presentNullableDouble(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new GoalError();
    }
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new GoalError();
    }
    const parsed = Number(value);
    if (value === '' || !Number.isFinite(parsed)) {
      throw new GoalError();
    }
    return;
  }
  throw new GoalError();
}

function presentNullableInt(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new GoalError();
    }
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new GoalError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return;
  }
  throw new GoalError();
}

function presentGeneratedGoalExtras(row: Record<string, unknown>): void {
  presentNullableString(row.advice);
  presentNullableString(row.desired_outcome);
  presentNullableString(row.goal_id);
  presentNullableString(row.goal_type);
  presentNullableString(row.source);
  presentNullableString(row.unit);
  presentNullableString(row.why_it_matters);
  presentUnusedStringListItems(row.success_criteria);
  presentNullableDate(row.created_at);
  presentNullableDate(row.updated_at);
  presentNullableDate(row.ended_at);
  presentNullableDate(row.horizon_at);
  presentNullableDouble(row.max_value);
  presentNullableDouble(row.min_value);
  presentNullableInt(row.focus_rank);
  presentNullableInt(row.latest_progress_sequence);
  if (
    row.metric === undefined ||
    row.metric === null ||
    typeof row.metric !== 'object' ||
    Array.isArray(row.metric)
  ) {
    return;
  }
  const metric = row.metric as Record<string, unknown>;
  presentNullableDouble(metric.current);
  presentNullableDouble(metric.target);
  presentNullableDouble(metric.max);
  presentNullableDouble(metric.min);
  presentNullableString(metric.type);
  presentNullableString(metric.unit);
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
    if (skipPaddedExtras(row)) {
      continue;
    }
    try {
      presentGeneratedGoalExtras(row);
    } catch {
      continue;
    }
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
