import { afterEach, describe, expect, it, vi } from 'vitest';

import { formatDateInputValue } from '@/lib/dateInput';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('formatDateInputValue', () => {
  it('keeps the local day for a time just after midnight east of UTC', () => {
    vi.stubEnv('TZ', 'Asia/Kolkata');

    expect(formatDateInputValue(new Date('2026-09-20T19:30:00Z'))).toBe('2026-09-21');
  });

  it('keeps the local day for a time late in the evening west of UTC', () => {
    vi.stubEnv('TZ', 'America/Los_Angeles');

    expect(formatDateInputValue(new Date('2026-09-22T03:00:00Z'))).toBe('2026-09-21');
  });

  it('pads single digit months and days', () => {
    vi.stubEnv('TZ', 'UTC');

    expect(formatDateInputValue(new Date('2026-01-05T10:00:00Z'))).toBe('2026-01-05');
  });
});
