/** Qualified activity v2, audited 2026-10-15. These are telemetry proxies, not signup truth.
 * The version string MUST move with any allowlist change: the 2026-10-15
 * evidence snapshot (09:27 UTC) was generated from the six wire events hours
 * before this fuller allowlist shipped (12:19 UTC), and its MAU (7,163) no
 * longer reproduces under the shipped definition (same window: 9,665). */
export const DEFINITION_VERSION = "qualified-v2-2026-10-15";
export const DAY_MS = 86_400_000;
export const PLATFORM_ORDER = [
  "macos",
  "ios",
  "android",
  "windows",
  "web",
  "integrations",
  "unknown",
] as const;
export type Platform = (typeof PLATFORM_ORDER)[number];
export const PLATFORM_SQL = `multiIf(properties.$lib = 'web','web', properties.$lib = 'omi-windows' AND properties.$os = 'Windows','windows', properties.$os_name = 'macOS','macos',properties.$os_name IN ('iOS','iPadOS'),'ios',properties.$os_name = 'Android','android','unknown')`;
export const EXCLUSIONS_SQL = `NOT startsWith(event,'cfc_') AND NOT startsWith(distinct_id,'cfc_')
 AND distinct_id != 'omi-release-probe' AND coalesce(toString(properties.uid),'') != 'omi-release-probe'
 AND coalesce(toString(properties.user_id),'') != 'omi-release-probe'`;
type Rule = { events: readonly string[]; guard?: string };
/** Call-site audit v2: allowlisted wire events and property guards, by platform. */
export const QUALIFIED_ALLOWLIST: Record<
  Platform,
  { foreground: Rule[]; saved: Rule[] }
> = {
  macos: {
    foreground: [
      {
        events: [
          "question_asked",
          "Chat Message Sent",
          "floating_bar_query_sent",
        ],
        guard:
          "NOT lower(coalesce(toString(properties.source),'')) LIKE '%onboarding%' AND NOT lower(coalesce(toString(properties.origin),'')) LIKE '%onboarding%' AND coalesce(toString(properties.automated),'false') != 'true'",
      },
      { events: ["Memory List Item Clicked"] },
      {
        events: ["Search Result Opened", "Conversation Opened From Search"],
        guard:
          "properties.search_surface IN ('conversations','memories','tasks')",
      },
    ],
    saved: [
      {
        events: ["Memory Created"],
        guard: "properties.conversation_source = 'desktop'",
      },
    ],
  },
  ios: mobileRules(),
  android: mobileRules(),
  windows: { foreground: [], saved: [] },
  web: { foreground: [], saved: [] },
  integrations: { foreground: [], saved: [] },
  unknown: { foreground: [], saved: [] },
};
function mobileRules(): { foreground: Rule[]; saved: Rule[] } {
  return {
    foreground: [
      {
        events: [
          "Phone Mic Recording Started",
          "Conversation List Item Clicked",
          "Conversation Opened From Search",
          "Live Transcript Card Clicked",
          "Action Item Completed",
          "Action Item Manually Added",
          "Action Item Edited",
          "Conversation Detail Search Query Entered",
          "Fact List Item Clicked",
        ],
      },
      {
        events: ["Conversation Action"],
        guard:
          "properties.action IN ('open','ask_omi','search','star','share','copy_transcript','copy_summary')",
      },
      {
        events: ["Fact Searched"],
        guard:
          "toIntOrZero(coalesce(toString(properties.query_length),'0')) > 0",
      },
      {
        events: ["Bottom Navigation Tab Clicked"],
        guard: "properties.tab IN ('Home','Tasks','Chat','Chat Voice')",
      },
      {
        events: ["Daily Summary Detail Viewed"],
        guard: "properties.source IS NULL",
      },
    ],
    saved: [
      {
        events: ["Memory Created"],
        guard:
          "properties.memory_result = 'saved' AND toString(properties.memory_discarded) = 'false' AND properties.memory_id IS NOT NULL AND properties.conversation_source IN ('omi','phone','apple_watch','openglass')",
      },
    ],
  };
}
function rulesSql(branch: "foreground" | "saved"): string {
  return (
    "(" +
    Object.entries(QUALIFIED_ALLOWLIST)
      .flatMap(([p, rules]) =>
        rules[branch].map(
          (rule) =>
            `(p='${p}' AND event IN (${rule.events
              .map((e) => `'${e}'`)
              .join(",")})${rule.guard ? ` AND (${rule.guard})` : ""})`
        )
      )
      .join(" OR ") +
    ")"
  );
}
export const QUALIFIED_EVENT_NAMES = Array.from(
  new Set(
    Object.values(QUALIFIED_ALLOWLIST).flatMap((p) =>
      [...p.foreground, ...p.saved].flatMap((r) => r.events)
    )
  )
);
export const FOREGROUND_SQL = rulesSql("foreground");
export const SAVED_CAPTURE_SQL = rulesSql("saved");
export const CAPTURE_TIME_SQL = `if(cap AND p IN ('ios','android'),parseDateTimeBestEffort(coalesce(toString(properties.timestamp),'1970-01-01')),timestamp)`;
export const PLATFORM_RANK_SQL = `multiIf(p='macos',1,p='ios',2,p='android',3,p='windows',4,p='web',5,p='integrations',6,7)`;
export const COVERAGE_REASON =
  "Telemetry proxy: no signup bridge/full staff roster; macOS saved-state/event-day proxy; mobile source-device/capture-time proxy; late capture, Windows/web/MCP undercovered.";

/** Exclusive UTC end; current partial day is never included. */
export function utcDay(now = new Date()): Date {
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
}
export function shiftDay(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}
export function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}
export function completeWindow(days: number, now = new Date(), offsetDays = 0) {
  const end = shiftDay(utcDay(now), -offsetDays);
  return { start: shiftDay(end, -days), end };
}
export function completeWeek(now = new Date(), weeksAgo = 0) {
  const day = utcDay(now);
  const end = shiftDay(day, -((day.getUTCDay() + 6) % 7) - weeksAgo * 7);
  return { start: shiftDay(end, -7), end };
}
export function sqlTime(date: Date): string {
  return `toDateTime('${date
    .toISOString()
    .slice(0, 19)
    .replace("T", " ")}', 'UTC')`;
}
export function freshness(
  refreshed: string | null,
  through: string | null,
  cadence: "hourly" | "daily" | "settled",
  now = new Date()
) {
  if (!refreshed || !through)
    return { stale: true, reason: "Source watermark unavailable" };
  const age = now.getTime() - Date.parse(refreshed);
  const stale =
    !Number.isFinite(age) ||
    age > (cadence === "hourly" ? 3_600_000 : DAY_MS) ||
    (cadence === "settled" &&
      through.slice(0, 10) < isoDay(shiftDay(utcDay(now), -2)));
  return { stale, reason: stale ? "Source refresh/window is stale" : null };
}
export interface Activity {
  platform: Platform;
  at: string;
}
export function primaryPlatform(activity: Activity[]): Platform {
  const rank = PLATFORM_ORDER.map((platform) => {
    const rows = activity.filter((a) => a.platform === platform);
    return {
      platform,
      days: new Set(rows.map((a) => new Date(a.at).toISOString().slice(0, 10)))
        .size,
      latest: Math.max(0, ...rows.map((a) => Date.parse(a.at))),
    };
  }).sort(
    (a, b) =>
      b.days - a.days ||
      b.latest - a.latest ||
      PLATFORM_ORDER.indexOf(a.platform) - PLATFORM_ORDER.indexOf(b.platform)
  );
  return rank[0].days ? rank[0].platform : "unknown";
}
export function entryPlatform(activity: Activity[]): Platform {
  return (
    activity
      .filter((a) => a.platform !== "unknown")
      .sort(
        (a, b) =>
          Date.parse(a.at) - Date.parse(b.at) ||
          PLATFORM_ORDER.indexOf(a.platform) -
            PLATFORM_ORDER.indexOf(b.platform)
      )[0]?.platform ?? "unknown"
  );
}
