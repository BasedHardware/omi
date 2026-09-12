import {
  importJobRowCopy,
  importJobStatusCopy,
  importJobTimestampCopy,
  loadOmiImportJobs,
  parseOmiImportJobs,
} from './legacyOmiImportJobs';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET import jobs and omits empty counts', () => {
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {
          job_id: 'job-1',
          status: 'completed',
          created_at: '2026-09-10T14:30:00.000Z',
          conversations_created: 3,
          conversations_skipped: 2,
          error: null,
        },
        {
          job_id: 'job-2',
          status: 'processing',
          processed_files: 3,
          total_files: 10,
          conversations_created: 0,
        },
        {
          job_id: 'job-3',
          status: 'failed',
          error: 'Zip could not be read.',
        },
        {job_id: 'job-4', status: 'queued'},
      ]),
    ),
  ).toEqual([
    {
      id: 'job-1',
      status: 'completed',
      createdAtMs: Date.parse('2026-09-10T14:30:00.000Z'),
      conversationsCreated: 3,
      conversationsSkipped: 2,
    },
    {
      id: 'job-2',
      status: 'processing',
      conversationsCreated: 0,
      processedFiles: 3,
      totalFiles: 10,
    },
    {id: 'job-3', status: 'failed', error: 'Zip could not be read.'},
    {id: 'job-4', status: 'queued'},
  ]);
});

test('names GET import job status without defaulting unknown to Pending', () => {
  expect(importJobStatusCopy('pending')).toBe('Pending');
  expect(importJobStatusCopy('processing')).toBe('Processing');
  expect(importJobStatusCopy('completed')).toBe('Completed');
  expect(importJobStatusCopy('failed')).toBe('Failed');
  expect(importJobStatusCopy('queued')).toBe('queued');
  expect(importJobStatusCopy('')).toBe('Status unavailable');
  expect(importJobStatusCopy(' \t')).toBe('Status unavailable');
});

test('names Flutter import timestamps from local midnight', () => {
  const created = new Date(2026, 8, 10, 14, 30).getTime();
  expect(importJobTimestampCopy(created, new Date(2026, 8, 10, 20, 0))).toBe(
    'Today at 14:30',
  );
  expect(importJobTimestampCopy(created, new Date(2026, 8, 11, 9, 0))).toBe(
    'Yesterday at 14:30',
  );
  expect(importJobTimestampCopy(created, new Date(2026, 8, 12, 9, 0))).toBe(
    '10/9/2026 at 14:30',
  );
});

test('names GET import job rows without inventing ETA or No imports yet', () => {
  const now = new Date(2026, 8, 10, 20, 0);
  expect(
    importJobRowCopy(
      {
        id: 'job-1',
        status: 'completed',
        createdAtMs: new Date(2026, 8, 10, 14, 30).getTime(),
        conversationsCreated: 3,
        conversationsSkipped: 2,
      },
      now,
    ),
  ).toBe('Completed · Today at 14:30 · 3 conversations · 2 skipped');
  expect(
    importJobRowCopy({
      id: 'job-2',
      status: 'processing',
      processedFiles: 3,
      totalFiles: 10,
    }),
  ).toBe('Processing · 3/10');
  expect(
    importJobRowCopy({
      id: 'job-2b',
      status: 'processing',
      totalFiles: 4,
    }),
  ).toBe('Processing · 0/4');
  expect(
    importJobRowCopy({
      id: 'job-3',
      status: 'failed',
      error: 'Zip could not be read.',
    }),
  ).toBe('Failed · Zip could not be read.');
  expect(importJobRowCopy({id: 'job-4', status: 'queued'})).toBe('queued');
});

test('does not omit a neighboring import job when stored counts are integer strings', () => {
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-kept', status: 'completed'},
        {
          job_id: 'job-string',
          status: 'completed',
          conversations_created: '3',
          conversations_skipped: '-1',
          processed_files: '1',
          total_files: '4',
        },
        {
          job_id: 'job-negative',
          status: 'completed',
          conversations_created: -1,
        },
      ]),
    ),
  ).toEqual([
    {id: 'job-kept', status: 'completed'},
    {
      id: 'job-string',
      status: 'completed',
      conversationsCreated: 3,
      conversationsSkipped: -1,
      processedFiles: 1,
      totalFiles: 4,
    },
    {id: 'job-negative', status: 'completed', conversationsCreated: -1},
  ]);
});

test('keeps GET import jobs when a job_id exceeds 256', () => {
  const id = 'j'.repeat(257);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: id, status: 'completed'},
        {
          job_id: 'job-neighbor',
          status: 'failed',
          error: 'Zip could not be read.',
        },
      ]),
    ),
  ).toEqual([
    {id, status: 'completed'},
    {id: 'job-neighbor', status: 'failed', error: 'Zip could not be read.'},
  ]);
});

test('keeps GET import jobs when created_at exceeds 100', () => {
  const createdAt = 'c'.repeat(101);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-long', status: 'completed', created_at: createdAt},
        {
          job_id: 'job-neighbor',
          status: 'failed',
          error: 'Zip could not be read.',
        },
      ]),
    ),
  ).toEqual([
    {id: 'job-long', status: 'completed'},
    {id: 'job-neighbor', status: 'failed', error: 'Zip could not be read.'},
  ]);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-null', status: 'completed', created_at: null},
        {job_id: 'job-kept', status: 'queued'},
      ]),
    ),
  ).toEqual([
    {id: 'job-null', status: 'completed'},
    {id: 'job-kept', status: 'queued'},
  ]);
});

test('keeps GET import jobs when error exceeds 10000', () => {
  const error = 'E'.repeat(10001);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-long-error', status: 'failed', error},
        {job_id: 'job-neighbor', status: 'completed'},
      ]),
    ),
  ).toEqual([
    {id: 'job-long-error', status: 'failed', error},
    {id: 'job-neighbor', status: 'completed'},
  ]);
});

test('fails closed for malformed GET import jobs', () => {
  expect(() => parseOmiImportJobs(JSON.stringify({}))).toThrow();
  expect(() =>
    parseOmiImportJobs(JSON.stringify([{status: 'completed'}])),
  ).toThrow();
  expect(() =>
    parseOmiImportJobs(JSON.stringify([{job_id: 'job-1', status: true}])),
  ).toThrow();
  expect(() =>
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-1', status: 'completed'},
        {job_id: 'job-1', status: 'failed'},
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-1', status: 'completed', conversations_created: 1.5},
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-1', status: 'completed', conversations_created: '3.0'},
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-1', status: 'completed', created_at: 1},
      ]),
    ),
  ).toThrow();
});

test('loadOmiImportJobs names GET rows and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'import-jobs',
    status: 200,
    body: JSON.stringify([
      {job_id: 'job-1', status: 'pending'},
      {job_id: 'job-2', status: 'completed', conversations_created: 1},
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiImportJobs(backend)).toEqual([
    {id: 'job-1', status: 'pending'},
    {id: 'job-2', status: 'completed', conversationsCreated: 1},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/import/jobs?limit=50',
  });
  expect(
    request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    request.mock.calls.some(call => String(call[0].path).includes('limitless')),
  ).toBe(false);
  request.mockResolvedValue({id: 'import-jobs', status: 404, body: null});
  expect(await loadOmiImportJobs(backend)).toEqual([]);
  request.mockResolvedValue({
    id: 'import-jobs',
    status: 200,
    body: JSON.stringify({jobs: []}),
  });
  expect(await loadOmiImportJobs(backend)).toEqual([]);
});
