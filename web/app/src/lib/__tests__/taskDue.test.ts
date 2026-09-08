import { describe, expect, it } from 'vitest';
import { daysUntilDue, formatDueBadge, formatDueStatus } from '../taskDue';

// Fixed local-time reference so the whole-day maths is deterministic.
const NOW = new Date(2026, 0, 15, 9, 30);
const at = (y: number, m: number, d: number, h = 12) =>
  new Date(y, m, d, h).toISOString();

describe('daysUntilDue', () => {
  it('floors both sides to local midnight', () => {
    expect(daysUntilDue(at(2026, 0, 15, 23), NOW)).toBe(0);
    expect(daysUntilDue(at(2026, 0, 15, 1), NOW)).toBe(0);
  });

  it('counts whole days late as negative', () => {
    expect(daysUntilDue(at(2026, 0, 13), NOW)).toBe(-2);
  });
});

describe('formatDueStatus', () => {
  it('singularises one day late', () => {
    expect(formatDueStatus(at(2026, 0, 14), NOW)).toEqual({
      text: '1 day late',
      isOverdue: true,
      isToday: false,
    });
  });

  it('pluralises multiple days late', () => {
    expect(formatDueStatus(at(2026, 0, 12), NOW).text).toBe('3 days late');
  });

  it('marks today without marking it overdue', () => {
    expect(formatDueStatus(at(2026, 0, 15, 23), NOW)).toEqual({
      text: 'Due today',
      isOverdue: false,
      isToday: true,
    });
  });

  it('names tomorrow and the coming week', () => {
    expect(formatDueStatus(at(2026, 0, 16), NOW).text).toBe('Due tomorrow');
    expect(formatDueStatus(at(2026, 0, 20), NOW).text).toContain('Due Tue');
  });

  it('drops the weekday beyond a week out', () => {
    const text = formatDueStatus(at(2026, 1, 3), NOW).text;
    expect(text).toBe('Due Feb 3');
  });
});

describe('formatDueBadge', () => {
  it('compacts overdue to a day count', () => {
    expect(formatDueBadge(at(2026, 0, 13), NOW)).toEqual({
      text: '2d late',
      isOverdue: true,
    });
  });

  it('uses relative words inside the week', () => {
    expect(formatDueBadge(at(2026, 0, 15), NOW).text).toBe('Today');
    expect(formatDueBadge(at(2026, 0, 16), NOW).text).toBe('Tomorrow');
    expect(formatDueBadge(at(2026, 0, 20), NOW).text).toBe('Tue');
  });

  it('falls back to a date beyond a week out', () => {
    expect(formatDueBadge(at(2026, 1, 3), NOW).text).toBe('Feb 3');
  });
});
