import {
  importJobEstimatedHoursCopy,
  importJobEstimatedMinutesCopy,
  importJobEstimatedRemainingCopy,
  importJobEstimatedTimeRemainingCopy,
  importJobLessThanAMinuteCopy,
  importJobPendingCopy,
  importJobRowCopy,
  importJobStatusCopy,
  importJobTimestampCopy,
  importJobsCopy,
  importJobsEmptyCopy,
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

test('names GET import job status unknown as Flutter Pending', () => {
  expect(importJobPendingCopy()).toBe('Pending');
  expect(importJobStatusCopy('pending')).toBe(importJobPendingCopy());
  expect(importJobStatusCopy('processing')).toBe('Processing');
  expect(importJobStatusCopy('completed')).toBe('Completed');
  expect(importJobStatusCopy('failed')).toBe('Failed');
  expect(importJobStatusCopy('queued')).toBe(importJobPendingCopy());
  expect(importJobStatusCopy('')).toBe(importJobPendingCopy());
  expect(importJobStatusCopy(' \t')).toBe(importJobPendingCopy());
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

test('names GET import job rows Flutter estimated remaining without inventing writes', () => {
  const now = new Date(2026, 8, 10, 20, 0);
  expect(importJobLessThanAMinuteCopy()).toBe('Less than a minute');
  expect(importJobEstimatedMinutesCopy(1)).toBe('~1 minute(s)');
  expect(importJobEstimatedHoursCopy(1)).toBe('~1 hour(s)');
  expect(
    importJobEstimatedTimeRemainingCopy(importJobLessThanAMinuteCopy()),
  ).toBe('Estimated: Less than a minute remaining');
  expect(importJobEstimatedRemainingCopy(3, 10)).toBe(
    'Estimated: Less than a minute remaining',
  );
  expect(importJobEstimatedRemainingCopy(0, 120)).toBe(
    'Estimated: ~1 minute(s) remaining',
  );
  expect(importJobEstimatedRemainingCopy(0, 7200)).toBe(
    'Estimated: ~1 hour(s) remaining',
  );
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
  ).toBe(
    'Processing · Estimated: Less than a minute remaining · 3/10',
  );
  expect(
    importJobRowCopy({
      id: 'job-2b',
      status: 'processing',
      totalFiles: 4,
    }),
  ).toBe('Processing · Estimated: Less than a minute remaining · 0/4');
  expect(
    importJobRowCopy({
      id: 'job-pending',
      status: 'pending',
      totalFiles: 4,
    }),
  ).toBe('Pending · Estimated: Less than a minute remaining · 0/4');
  expect(
    importJobRowCopy({
      id: 'job-queued',
      status: 'queued',
      totalFiles: 4,
    }),
  ).toBe('Pending · Estimated: Less than a minute remaining · 0/4');
  expect(
    importJobRowCopy({
      id: 'job-3',
      status: 'failed',
      error: 'Zip could not be read.',
    }),
  ).toBe('Failed · Zip could not be read.');
  expect(importJobRowCopy({id: 'job-4', status: 'queued'})).toBe(
    importJobPendingCopy(),
  );
  expect(
    importJobRowCopy({
      id: 'job-done-files',
      status: 'completed',
      processedFiles: 3,
      totalFiles: 10,
    }),
  ).toBe('Completed');
});

test('names GET empty import jobs as Flutter No imports yet', () => {
  expect(importJobsEmptyCopy()).toBe('No imports yet');
  expect(importJobsCopy([])).toEqual([
    {key: 'empty', title: 'Import Data', copy: importJobsEmptyCopy()},
  ]);
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

test('keeps GET import jobs when a job_id exceeds 10000', () => {
  const id = 'j'.repeat(10001);
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

test('fails closed when a job_id exceeds 1000000', () => {
  expect(() =>
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'j'.repeat(1_000_001), status: 'completed'},
        {
          job_id: 'job-neighbor',
          status: 'failed',
          error: 'Zip could not be read.',
        },
      ]),
    ),
  ).toThrow();
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

test('keeps GET import jobs when created_at uses hour-only offsets Dart DateTime.tryParse accepts', () => {
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {
          job_id: 'job-hour',
          status: 'completed',
          created_at: '2026-09-10T14:30:00+00',
        },
        {
          job_id: 'job-neighbor',
          status: 'failed',
          error: 'Zip could not be read.',
        },
      ]),
    ),
  ).toEqual([
    {
      id: 'job-hour',
      status: 'completed',
      createdAtMs: Date.parse('2026-09-10T14:30:00.000Z'),
    },
    {id: 'job-neighbor', status: 'failed', error: 'Zip could not be read.'},
  ]);
});

test('keeps GET import jobs when created_at exceeds 10000', () => {
  const createdAt = 'c'.repeat(10001);
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

test('keeps GET import jobs when status exceeds 64', () => {
  const status = 's'.repeat(65);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-long-status', status},
        {job_id: 'job-neighbor', status: 'completed'},
      ]),
    ),
  ).toEqual([
    {id: 'job-long-status', status},
    {id: 'job-neighbor', status: 'completed'},
  ]);
});

test('keeps GET import jobs when status exceeds 10000', () => {
  const status = 's'.repeat(10001);
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-long-status', status},
        {job_id: 'job-neighbor', status: 'completed'},
      ]),
    ),
  ).toEqual([
    {id: 'job-long-status', status},
    {id: 'job-neighbor', status: 'completed'},
  ]);
});

test('keeps GET import jobs when created_at is a non-string', () => {
  expect(
    parseOmiImportJobs(
      JSON.stringify([
        {job_id: 'job-numeric-clock', status: 'completed', created_at: 1},
        {
          job_id: 'job-neighbor',
          status: 'failed',
          error: 'Zip could not be read.',
        },
      ]),
    ),
  ).toEqual([
    {id: 'job-numeric-clock', status: 'completed'},
    {id: 'job-neighbor', status: 'failed', error: 'Zip could not be read.'},
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
