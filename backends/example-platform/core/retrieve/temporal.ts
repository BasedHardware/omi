import type { PersistedValidTime, ResolvedTimeInterval, TypedTemporalExpr } from "../schema";
export type { PersistedValidTime, ResolvedTimeInterval, TypedTemporalExpr } from "../schema";

/** Explicit inputs make temporal resolution hermetic: neither variant reads an ambient clock. */
export interface ReferenceClock {
  query_at: string;
  capture_at?: string;
}

/** End is exclusive. Imprecise expressions deliberately retain only their supplied coarse bucket. */
export type TimeInterval = ResolvedTimeInterval;

type LocalDate = { year: number; month: number; day: number };
const dateFormatters = new Map<string, Intl.DateTimeFormat>();
const offsetFormatters = new Map<string, Intl.DateTimeFormat>();
const rfc3339WithOffset = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$/;
/** Never let Date parse an offsetless string in the process's ambient timezone. */
const explicitInstant = (value: string, purpose: string): Date => {
  if (!rfc3339WithOffset.test(value)) throw new Error(`${purpose} must be an RFC3339 timestamp with an explicit offset: ${value}`);
  const result = new Date(value);
  if (Number.isNaN(result.valueOf())) throw new Error(`invalid ${purpose}: ${value}`);
  return result;
};

const formatter = (timezone: string): Intl.DateTimeFormat => {
  let value = dateFormatters.get(timezone);
  if (!value) {
    value = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" });
    dateFormatters.set(timezone, value);
  }
  return value;
};
const offsetFormatter = (timezone: string): Intl.DateTimeFormat => {
  let value = offsetFormatters.get(timezone);
  if (!value) {
    value = new Intl.DateTimeFormat("en-US", { timeZone: timezone, timeZoneName: "longOffset", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    offsetFormatters.set(timezone, value);
  }
  return value;
};
const localDateAt = (instant: string, timezone: string): LocalDate => {
  const time = explicitInstant(instant, "reference clock");
  const parts = Object.fromEntries(formatter(timezone).formatToParts(time).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return { year: Number(parts.year), month: Number(parts.month), day: Number(parts.day) };
};
const offsetMinutesAt = (instantMs: number, timezone: string): number => {
  const value = offsetFormatter(timezone).formatToParts(new Date(instantMs)).find((part) => part.type === "timeZoneName")?.value;
  const match = value?.match(/^GMT([+-])(\d{2}):(\d{2})$/);
  if (!match) throw new Error(`unsupported timezone or offset: ${timezone}`);
  return (match[1] === "+" ? 1 : -1) * (Number(match[2]) * 60 + Number(match[3]));
};
/** Calendar boundaries are local midnights. Iteration accounts for the offset selected by that local date. */
const localMidnight = (date: LocalDate, timezone: string): string => {
  const nominalUtc = Date.UTC(date.year, date.month - 1, date.day);
  let instant = nominalUtc - offsetMinutesAt(nominalUtc, timezone) * 60_000;
  instant = nominalUtc - offsetMinutesAt(instant, timezone) * 60_000;
  return new Date(instant).toISOString();
};
const addDays = (date: LocalDate, days: number): LocalDate => {
  const next = new Date(Date.UTC(date.year, date.month - 1, date.day + days));
  return { year: next.getUTCFullYear(), month: next.getUTCMonth() + 1, day: next.getUTCDate() };
};
const addMonths = (date: LocalDate, months: number): LocalDate => {
  const next = new Date(Date.UTC(date.year, date.month - 1 + months, 1));
  return { year: next.getUTCFullYear(), month: next.getUTCMonth() + 1, day: 1 };
};
const startOf = (date: LocalDate, unit: Exclude<Extract<TypedTemporalExpr, { kind: "relative" }> ["unit"], "instant">): LocalDate => {
  if (unit === "day") return date;
  if (unit === "week") return addDays(date, -((new Date(Date.UTC(date.year, date.month - 1, date.day)).getUTCDay() + 6) % 7));
  if (unit === "month") return { ...date, day: 1 };
  if (unit === "quarter") return { year: date.year, month: Math.floor((date.month - 1) / 3) * 3 + 1, day: 1 };
  return { year: date.year, month: 1, day: 1 };
};
const advance = (date: LocalDate, unit: Exclude<Extract<TypedTemporalExpr, { kind: "relative" }> ["unit"], "instant">, amount: number): LocalDate =>
  unit === "day" ? addDays(date, amount) : unit === "week" ? addDays(date, amount * 7) : unit === "month" ? addMonths(date, amount) : unit === "quarter" ? addMonths(date, amount * 3) : { year: date.year + amount, month: 1, day: 1 };
const calendarInterval = (start: LocalDate, unit: Exclude<Extract<TypedTemporalExpr, { kind: "relative" }> ["unit"], "instant">, timezone: string): TimeInterval =>
  ({ kind: "calendar_interval", start: localMidnight(start, timezone), end: localMidnight(advance(start, unit, 1), timezone), timezone, granularity: unit });
const absoluteStart = (granularity: Exclude<Extract<TypedTemporalExpr, { kind: "absolute" }> ["granularity"], "instant">, value: string): LocalDate => {
  const year = /^(\d{4})$/.exec(value)?.[1];
  if (granularity === "year" && year) return { year: Number(year), month: 1, day: 1 };
  const month = /^(\d{4})-(\d{2})$/.exec(value);
  if (granularity === "month" && month && Number(month[2]) >= 1 && Number(month[2]) <= 12) return { year: Number(month[1]), month: Number(month[2]), day: 1 };
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (granularity === "day" && day) {
    const result = { year: Number(day[1]), month: Number(day[2]), day: Number(day[3]) };
    if (localMidnight(result, "UTC").slice(0, 10) === value) return result;
  }
  const quarter = /^(\d{4})-Q([1-4])$/.exec(value);
  if (granularity === "quarter" && quarter) return { year: Number(quarter[1]), month: (Number(quarter[2]) - 1) * 3 + 1, day: 1 };
  const week = /^(\d{4})-W(\d{2})$/.exec(value);
  if (granularity === "week" && week && Number(week[2]) >= 1 && Number(week[2]) <= 53) {
    const jan4 = new Date(Date.UTC(Number(week[1]), 0, 4));
    const monday = addDays({ year: Number(week[1]), month: 1, day: 4 }, -((jan4.getUTCDay() + 6) % 7) + (Number(week[2]) - 1) * 7);
    return monday;
  }
  throw new Error(`invalid ${granularity} temporal value: ${value}`);
};

export const resolveTemporal = (expr: TypedTemporalExpr, referenceClock: ReferenceClock, timezone: string): TimeInterval => {
  // Constructing formatters validates IANA zones without consulting ambient time.
  formatter(timezone);
  if (expr.kind === "imprecise") return { kind: "imprecise", bucket: expr.bucket, precision: expr.precision, timezone };
  if (expr.kind === "absolute") {
    if (expr.granularity === "instant") {
      const instant = explicitInstant(expr.value, "instant temporal value");
      return { kind: "instant", start: instant.toISOString(), end: instant.toISOString(), timezone, granularity: "instant" };
    }
    return calendarInterval(absoluteStart(expr.granularity, expr.value), expr.granularity, timezone);
  }
  const clock = expr.anchor === "query" ? referenceClock.query_at : referenceClock.capture_at;
  if (!clock) throw new Error("capture-anchored temporal expression requires capture_at");
  const start = advance(startOf(localDateAt(clock, timezone), expr.unit), expr.unit, expr.offset);
  return calendarInterval(start, expr.unit, timezone);
};

/**
 * The sole construction helper for persisted temporal truth. It intentionally
 * delegates arithmetic to G0's resolver and records every derivation input
 * needed to interpret the resulting interval after a restart.
 */
export const persistValidTime = (expr: TypedTemporalExpr, referenceClock: ReferenceClock, timezone: string, resolver_version = "g0-temporal-resolver-v1"): PersistedValidTime => ({
  typed_expression: expr,
  resolved_interval: resolveTemporal(expr, referenceClock, timezone),
  derivation: { resolver_version, timezone },
});
