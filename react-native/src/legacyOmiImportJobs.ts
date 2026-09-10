import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_IMPORT_JOBS = 50;

class ImportJobError extends Error {
  constructor() {
    super('Omi import jobs are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ImportJobError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new ImportJobError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new ImportJobError();
  }
  return value;
}

function optionalCount(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new ImportJobError();
  }
  return value;
}

function createdAtMs(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const raw = visibleDisplayText(text(value, 100));
  if (raw === '') {
    return undefined;
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

export type OmiImportJob = {
  id: string;
  status: string;
  createdAtMs?: number;
  conversationsCreated?: number;
  conversationsSkipped?: number;
  processedFiles?: number;
  totalFiles?: number;
  error?: string;
};

export type OmiImportJobRow = {
  key: string;
  title: string;
  copy: string;
};

export function importJobStatusCopy(status: string): string {
  const trimmed = visibleDisplayText(status);
  if (trimmed === 'pending') {
    return 'Pending';
  }
  if (trimmed === 'processing') {
    return 'Processing';
  }
  if (trimmed === 'completed') {
    return 'Completed';
  }
  if (trimmed === 'failed') {
    return 'Failed';
  }
  return trimmed === '' ? 'Status unavailable' : trimmed;
}

export function importJobTimestampCopy(
  createdAtMs: number,
  now: Date = new Date(),
): string {
  if (!Number.isFinite(createdAtMs) || createdAtMs <= 0) {
    return '';
  }
  const local = new Date(createdAtMs);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const jobDay = new Date(
    local.getFullYear(),
    local.getMonth(),
    local.getDate(),
  );
  const time = `${String(local.getHours()).padStart(2, '0')}:${String(
    local.getMinutes(),
  ).padStart(2, '0')}`;
  if (jobDay.getTime() === today.getTime()) {
    return `Today at ${time}`;
  }
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (jobDay.getTime() === yesterday.getTime()) {
    return `Yesterday at ${time}`;
  }
  return `${local.getDate()}/${
    local.getMonth() + 1
  }/${local.getFullYear()} at ${time}`;
}

export function importJobRowCopy(
  job: OmiImportJob,
  now: Date = new Date(),
): string {
  const parts = [importJobStatusCopy(job.status)];
  if (
    visibleDisplayText(job.status) === 'completed' &&
    typeof job.createdAtMs === 'number'
  ) {
    const stamp = importJobTimestampCopy(job.createdAtMs, now);
    if (stamp !== '') {
      parts.push(stamp);
    }
  }
  if (
    typeof job.conversationsCreated === 'number' &&
    job.conversationsCreated > 0
  ) {
    parts.push(`${job.conversationsCreated} conversations`);
  }
  if (
    typeof job.conversationsSkipped === 'number' &&
    job.conversationsSkipped > 0
  ) {
    parts.push(`${job.conversationsSkipped} skipped`);
  }
  if (
    visibleDisplayText(job.status) === 'processing' &&
    typeof job.totalFiles === 'number' &&
    job.totalFiles > 0
  ) {
    const processed =
      typeof job.processedFiles === 'number' ? job.processedFiles : 0;
    parts.push(`${processed}/${job.totalFiles}`);
  }
  const error = visibleDisplayText(job.error ?? '');
  if (error !== '') {
    parts.push(error);
  }
  return parts.join(' · ');
}

export function importJobsCopy(
  jobs: readonly OmiImportJob[],
  now: Date = new Date(),
): OmiImportJobRow[] {
  return jobs.map(job => ({
    key: job.id,
    title: 'Import Data',
    copy: importJobRowCopy(job, now),
  }));
}

export function parseOmiImportJobs(body: string): OmiImportJob[] {
  const rows = array(JSON.parse(body), MAX_IMPORT_JOBS);
  const items: OmiImportJob[] = [];
  const seen = new Set<string>();
  for (const raw of rows) {
    const row = object(raw);
    const id = visibleDisplayText(text(row.job_id, 256));
    if (id === '') {
      throw new ImportJobError();
    }
    if (seen.has(id)) {
      throw new ImportJobError();
    }
    seen.add(id);
    const status = visibleDisplayText(text(row.status, 64));
    const created = createdAtMs(row.created_at);
    const conversationsCreated = optionalCount(row.conversations_created);
    const conversationsSkipped = optionalCount(row.conversations_skipped);
    const processedFiles = optionalCount(row.processed_files);
    const totalFiles = optionalCount(row.total_files);
    const error =
      row.error === undefined || row.error === null
        ? ''
        : visibleDisplayText(text(row.error, 10000));
    items.push({
      id,
      status,
      ...(created === undefined ? {} : {createdAtMs: created}),
      ...(conversationsCreated === undefined ? {} : {conversationsCreated}),
      ...(conversationsSkipped === undefined ? {} : {conversationsSkipped}),
      ...(processedFiles === undefined ? {} : {processedFiles}),
      ...(totalFiles === undefined ? {} : {totalFiles}),
      ...(error === '' ? {} : {error}),
    });
  }
  return items;
}

export async function loadOmiImportJobs(
  backend: OmiBackend,
): Promise<OmiImportJob[]> {
  const response = await backend.request({
    id: 'omi-import-jobs',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/import/jobs?limit=50',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiImportJobs(response.body);
  } catch {
    return [];
  }
}
