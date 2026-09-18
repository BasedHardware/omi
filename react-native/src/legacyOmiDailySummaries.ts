import type {OmiBackend} from './omiNativeTypes';
import {
  dailySummaryDefaultHeadlineCopy,
  visibleDisplayText,
} from './desktopReadClient';

const MAX_DAILY_SUMMARIES = 3;

class DailySummaryError extends Error {
  constructor() {
    super('Omi daily summaries are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new DailySummaryError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new DailySummaryError();
  }
  return value;
}

function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new DailySummaryError();
  }
  return value;
}

export type OmiDailySummary = {
  id: string;
  date: string;
  headline: string;
  overview?: string;
  dayEmoji?: string;
  conversations?: number;
  actionItems?: number;
  durationMinutes?: number;
  watchingMinutes?: number;
  proactiveMoments?: number;
};

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new DailySummaryError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new DailySummaryError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new DailySummaryError();
  }
}

function presentNullableDouble(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new DailySummaryError();
    }
    if (value === '' || !Number.isFinite(Number(value))) {
      throw new DailySummaryError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return;
  }
  throw new DailySummaryError();
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
    if (typeof item !== 'string') {
      throw new DailySummaryError();
    }
  }
}

function presentObjectListStrings(value: unknown, fields: string[]): void {
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    const row = object(raw);
    for (const field of fields) {
      presentNullableString(row[field]);
    }
  }
}

function presentHighlights(value: unknown): void {
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    const row = object(raw);
    presentNullableString(row.topic);
    presentNullableString(row.emoji);
    presentNullableString(row.summary);
    presentUnusedStringListItems(row.conversation_ids);
  }
}

function presentLocations(value: unknown): void {
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    const pin = object(raw);
    presentNullableDouble(pin.latitude);
    presentNullableDouble(pin.longitude);
    presentNullableString(pin.address);
    presentNullableString(pin.conversation_id);
    presentNullableString(pin.time);
  }
}

function presentMemoriesLearned(value: unknown): void {
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    const memory = object(raw);
    presentNullableDate(memory.captured_at);
    presentNullableString(memory.category);
    presentNullableString(memory.content);
    presentNullableString(memory.memory_id);
  }
}

function optionalCount(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new DailySummaryError();
    }
    if (!/^[0-9]+$/.test(value)) {
      throw new DailySummaryError();
    }
    const parsed = Number(value);
    return parsed === 0 ? undefined : parsed;
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw new DailySummaryError();
  }
  if (value < 0) {
    return undefined;
  }
  return value === 0 ? undefined : value;
}

function optionalWireString(value: unknown, limit: number): string {
  if (value === undefined || value === null) {
    return '';
  }
  return visibleDisplayText(text(value, limit));
}

function summaryId(value: unknown): string | null {
  if (value === undefined || value === null) {
    return '';
  }
  return text(value, 1_000_000);
}

function summaryDate(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  return text(value, 1_000_000);
}

function headlineCopy(value: unknown): string | undefined {
  if (value === undefined || value === null) {
    return dailySummaryDefaultHeadlineCopy();
  }
  return text(value, 1_000_000);
}

function summaryStats(value: unknown): {
  conversations?: number;
  actionItems?: number;
  durationMinutes?: number;
  watchingMinutes?: number;
  proactiveMoments?: number;
} {
  if (value === undefined || value === null) {
    return {};
  }
  if (typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  const stats = value as Record<string, unknown>;
  const conversations = optionalCount(stats.total_conversations);
  const actionItems = optionalCount(stats.action_items_count);
  const durationMinutes = optionalCount(stats.total_duration_minutes);
  const watchingMinutes = optionalCount(stats.watching_minutes);
  const proactiveMoments = optionalCount(stats.proactive_moments);
  optionalCount(stats.action_items_created);
  optionalCount(stats.memories_created);
  return {
    ...(conversations === undefined ? {} : {conversations}),
    ...(actionItems === undefined ? {} : {actionItems}),
    ...(durationMinutes === undefined ? {} : {durationMinutes}),
    ...(watchingMinutes === undefined ? {} : {watchingMinutes}),
    ...(proactiveMoments === undefined ? {} : {proactiveMoments}),
  };
}

export function parseOmiDailySummaries(body: string): OmiDailySummary[] {
  const row = object(JSON.parse(body));
  const summaries =
    row.summaries === undefined || row.summaries === null
      ? []
      : array(row.summaries);
  const items: OmiDailySummary[] = [];
  const seen = new Set<string>();
  for (const raw of summaries) {
    if (items.length === MAX_DAILY_SUMMARIES) {
      break;
    }
    const summary = object(raw);
    const id = summaryId(summary.id);
    if (id === null) {
      continue;
    }
    const headline = headlineCopy(summary.headline);
    if (headline === undefined) {
      continue;
    }
    if (id !== '') {
      if (seen.has(id)) {
        throw new DailySummaryError();
      }
      seen.add(id);
    }
    const date = summaryDate(summary.date);
    const dayEmoji = optionalWireString(summary.day_emoji, 1_000_000);
    const overview = optionalWireString(summary.overview, 1_000_000);
    presentNullableDate(summary.created_at);
    presentLocations(summary.locations);
    presentMemoriesLearned(summary.memories_learned);
    presentObjectListStrings(summary.action_items, [
      'description',
      'priority',
      'source_conversation_id',
    ]);
    presentHighlights(summary.highlights);
    presentObjectListStrings(summary.decisions_made, [
      'decision',
      'conversation_id',
    ]);
    presentObjectListStrings(summary.knowledge_nuggets, [
      'insight',
      'conversation_id',
    ]);
    presentObjectListStrings(summary.unresolved_questions, [
      'question',
      'conversation_id',
    ]);
    const stats = summaryStats(summary.stats);
    items.push({
      id,
      date,
      headline,
      ...(overview === '' ? {} : {overview}),
      ...(dayEmoji === '' ? {} : {dayEmoji}),
      ...stats,
    });
  }
  return items;
}

export async function loadOmiDailySummaries(
  backend: OmiBackend,
): Promise<OmiDailySummary[]> {
  const response = await backend.request({
    id: 'omi-daily-summaries',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summaries?limit=3&offset=0',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiDailySummaries(response.body);
  } catch {
    return [];
  }
}
