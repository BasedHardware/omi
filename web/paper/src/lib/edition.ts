/**
 * The Edition, as the backend sends it.
 *
 * Field-for-field with the `Edition` model in `backend/models/paper.py`. Every block
 * is optional by construction: a quiet day yields a short paper, and a block with
 * nothing worth printing is omitted rather than padded.
 */

export interface Lede {
  headline: string;
  body?: string;
  source_date?: string;
}

export interface OpenLoop {
  question: string;
  first_raised?: string;
  days_open?: number;
}

export interface Counterpoint {
  position: string;
  argument: string;
  days_asserted?: number;
  first_asserted?: string;
}

export interface DeskItem {
  name: string;
  context?: string;
  last_mentioned?: string;
  days_since?: number;
}

export interface MarginNote {
  insight: string;
  source_date?: string;
}

export interface Edition {
  date: string;
  issue_number?: number;
  tier?: 'brief' | 'edition';
  lede?: Lede | null;
  open_loops?: OpenLoop[];
  counterpoint?: Counterpoint | null;
  desk?: DeskItem[];
  margin?: MarginNote | null;
}

/** Mirrors `Edition.is_empty`: not enough signal to print anything at all. */
export function isEmptyEdition(edition: Edition): boolean {
  return !(
    edition.lede ||
    edition.open_loops?.length ||
    edition.counterpoint ||
    edition.desk?.length ||
    edition.margin
  );
}

/** Today in the reader's own timezone, as `yyyy-mm-dd` — the paper is a local day. */
export function localToday(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * `SUNDAY, AUGUST 2, 2026` — mirrors `_dateline` in `backend/utils/paper/render.py`,
 * including its fallback to the raw string when the date will not parse.
 */
export function dateline(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return isoDate;
  const [, year, month, day] = match;
  // Constructed locally on purpose: `new Date('2026-08-02')` is parsed as UTC and
  // slips a day west of Greenwich.
  const parsed = new Date(Number(year), Number(month) - 1, Number(day));
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed
    .toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    })
    .toUpperCase();
}

/** `OPEN 1 DAY` / `OPEN 6 DAYS` — mirrors `_age`. The age is the point of the block. */
export function age(days: number): string {
  return days === 1 ? 'OPEN 1 DAY' : `OPEN ${days} DAYS`;
}

/** `QUIET 1 DAY` / `QUIET 9 DAYS` — mirrors `_silence`, with its label. */
export function silence(days: number): string {
  return days === 1 ? 'QUIET 1 DAY' : `QUIET ${days} DAYS`;
}
