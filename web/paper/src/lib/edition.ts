/**
 * The Edition, as the backend sends it.
 *
 * Field-for-field with the `Edition` model in `backend/models/paper.py`. Every
 * section is optional by construction: a quiet day yields a short paper, and a
 * section with nothing worth printing is omitted rather than padded.
 *
 * Two rules carry across the wire. Anything asserted about the outside world
 * names its source, and a run reports which sources failed — a paper that has
 * quietly had no Gmail for a fortnight must say so rather than look quiet.
 */

export interface SourceRef {
  name: string;
  url?: string;
}

export interface Claim {
  text: string;
  sources?: SourceRef[];
  provenance?: 'reported' | 'derived' | 'unverified';
  confidence?: number;
  note?: string;
}

export interface FocusBlock {
  label: string;
  minutes?: number;
  detail?: string;
}

export interface Yesterday {
  headline?: string;
  story?: string;
  focus?: FocusBlock[];
  decisions?: string[];
  unacted?: string;
  source_date?: string;
}

export interface CalendarEntry {
  title: string;
  start?: string;
  end?: string;
  attendees?: string[];
  location?: string;
}

export interface Commitment {
  text: string;
  due?: string;
  source?: string;
}

export interface Today {
  events?: CalendarEntry[];
  commitments?: Commitment[];
  note?: string;
}

export interface NewsletterStory {
  summary: string;
  sources?: SourceRef[];
  why?: string;
}

export interface PaperItem {
  title: string;
  authors?: string;
  submitted?: string;
  identifier?: string;
  url?: string;
  what_it_says?: string;
  why_it_matters?: string;
  experiment?: string;
}

export interface ToolItem {
  name: string;
  what?: string;
  why?: string;
  source?: SourceRef | null;
}

export interface NewsLine {
  category: string;
  claim: Claim;
}

export interface ForYou {
  papers?: PaperItem[];
  tools?: ToolItem[];
  news?: NewsLine[];
}

export interface Photo {
  moment?: string;
  caption?: string;
  prompt?: string;
  image_b64?: string;
}

export interface SourceHealth {
  source: string;
  ok?: boolean;
  fetched?: number;
  kept?: number;
  note?: string;
}

export interface Cover {
  thesis?: string;
  emphasis?: string;
  standfirst?: string;
}

export interface HeldBack {
  item: string;
  reason: string;
}

export interface Edition {
  date: string;
  issue_number?: number;
  tier?: 'brief' | 'edition';
  cover?: Cover;
  photo?: Photo | null;
  yesterday?: Yesterday | null;
  today?: Today | null;
  newsletters?: NewsletterStory[];
  for_you?: ForYou;
  held_back?: HeldBack[];
  source_health?: SourceHealth[];
}

/** Mirrors `ForYou.is_empty`. */
export function isForYouEmpty(forYou?: ForYou): boolean {
  return !(forYou?.papers?.length || forYou?.tools?.length || forYou?.news?.length);
}

/** Mirrors `Today.is_clear` — nothing scheduled and nothing owed. */
export function isTodayClear(today?: Today | null): boolean {
  return !(today?.events?.length || today?.commitments?.length);
}

/** Mirrors `Photo.is_printable`: an image with no real moment behind it is decoration. */
export function isPhotoPrintable(photo?: Photo | null): boolean {
  return Boolean(photo?.image_b64 && photo?.moment?.trim());
}

/** Mirrors `Edition.is_empty`: not enough signal to print anything at all. */
export function isEmptyEdition(edition: Edition): boolean {
  return !(
    edition.yesterday ||
    edition.today ||
    edition.newsletters?.length ||
    !isForYouEmpty(edition.for_you) ||
    edition.photo
  );
}

/** Mirrors `Edition.degraded_sources`. Printed, never swallowed. */
export function degradedSources(edition: Edition): SourceHealth[] {
  return (edition.source_health ?? []).filter((health) => health.ok === false);
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

/** `1h 40m` / `25m` — mirrors `_hours`. Focus time as a person would say it. */
export function hours(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${h}h` : `${h}h ${rest}m`;
}

/** `09:30` from an ISO timestamp, or empty when there isn't one — mirrors `_clock`. */
export function clock(isoStamp?: string): string {
  if (!isoStamp || isoStamp.length < 16) return '';
  return isoStamp.slice(11, 16);
}
