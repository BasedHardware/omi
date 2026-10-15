import { POSTHOG_SERVED_MAX_ROWS, withRowLimit } from "@/lib/posthog";

export type MobileOnboardingKind = "first-run" | "tutorial" | "attach";
type Step = { key: string; label: string; event: string; optional?: boolean };

// Audit §1: events fire on LEAVE. Independent person counts are intentional:
// signed-in users skip Auth, saved speech is optional, and Setup is flag-gated.
export const MOBILE_STEPS: Step[] = [
  { key: "auth", label: "Auth", event: "Onboarding Step Auth Completed" },
  {
    key: "consent",
    label: "AI consent",
    event: "Onboarding Step AI Consent Completed",
  },
  { key: "name", label: "Name", event: "Onboarding Step Name Completed" },
  {
    key: "language",
    label: "Primary language",
    event: "Onboarding Step Primary Language Completed",
  },
  {
    key: "acquisition",
    label: "Acquisition source",
    event: "Onboarding Step Acquisition Source Completed",
  },
  {
    key: "permissions",
    label: "Permissions",
    event: "Onboarding Step Permissions Completed",
  },
  {
    key: "speech",
    label: "Guided intro saved",
    event: "Guided Intro Completed",
    optional: true,
  },
  {
    key: "knowledge",
    label: "Knowledge graph",
    event: "Onboarding Step Knowledge Graph Completed",
  },
  {
    key: "setup",
    label: "Setup (flag-gated)",
    event: "Onboarding Step Setup Completed",
    optional: true,
  },
  { key: "completed", label: "Completed", event: "Onboarding Completed" },
];
export const TUTORIAL_STEPS = [
  "transcription_demo",
  "single_press_ask_question",
  "voice_reply",
  "power_cycle",
  "double_press_config",
  "all_set",
];
const ACTOR = "COALESCE(person_id, distinct_id)";
const MOBILE = "properties.platform IN ('ios', 'android')";
const quote = (s: string) => `'${s.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;

function firstRunQuery(days: number) {
  return `WITH entrants AS (
    SELECT ${ACTOR} AS actor_id, min(timestamp) AS entered_at
    FROM events WHERE event = 'Product Journey Started'
      AND properties.journey = 'onboarding' AND properties.surface = 'onboarding'
      AND ${MOBILE} AND timestamp >= now() - INTERVAL ${days} DAY
    GROUP BY actor_id
  )
  SELECT ${ACTOR} AS actor_id, event
  FROM events JOIN entrants ON ${ACTOR} = entrants.actor_id
  WHERE event IN (${MOBILE_STEPS.map((s) => quote(s.event)).join(", ")})
    AND ${MOBILE} AND timestamp >= now() - INTERVAL ${days} DAY
    AND timestamp >= entrants.entered_at
    AND (event != 'Guided Intro Completed' OR
      (properties.completion_mode = 'saved' AND properties.source = 'first_run'))
  GROUP BY actor_id, event
  UNION ALL SELECT actor_id, 'Product Journey Started' AS event FROM entrants
  LIMIT ${POSTHOG_SERVED_MAX_ROWS}`;
}

function tutorialQuery(days: number) {
  // Keep every Started (including settings) and timestamp. The consumer closes
  // the preceding attempt at a new start or terminal; filtering starts to auto
  // in SQL would incorrectly attribute settings outcomes to an earlier auto.
  return `SELECT ${ACTOR} AS actor_id, event, toString(properties.step) AS step,
    toString(properties.source) AS source, timestamp AS event_at
  FROM events
  WHERE event IN ('Device Onboarding Started', 'Device Onboarding Step Completed',
    'Device Onboarding Completed', 'Device Onboarding Abandoned')
    AND ${MOBILE} AND timestamp >= now() - INTERVAL ${days} DAY
  GROUP BY actor_id, event, step, source, event_at
  ORDER BY actor_id, event_at, event
  LIMIT ${POSTHOG_SERVED_MAX_ROWS}`;
}

function attachQuery(days: number) {
  return `WITH completers AS (
    SELECT ${ACTOR} AS actor_id, min(timestamp) AS completed_at
    FROM events WHERE event = 'Onboarding Completed' AND ${MOBILE}
      AND timestamp >= now() - INTERVAL ${days} DAY
    GROUP BY actor_id
  ), pairs AS (
    SELECT ${ACTOR} AS actor_id, timestamp AS paired_at FROM events
    WHERE event = 'Device Paired' AND properties.hardware_family = 'omi_cv1'
      AND ${MOBILE} AND timestamp >= now() - INTERVAL ${days} DAY
  )
  SELECT completers.actor_id,
    dateDiff('second', completed_at, now()) AS age_seconds,
    minIf(dateDiff('second', completed_at, paired_at),
      paired_at > completed_at AND paired_at <= completed_at + INTERVAL 30 DAY) AS attach_seconds
  FROM completers LEFT JOIN pairs ON completers.actor_id = pairs.actor_id
  GROUP BY completers.actor_id, completed_at
  LIMIT ${POSTHOG_SERVED_MAX_ROWS}`;
}

export class PostHogError extends Error {
  constructor(public status: number) {
    super(`PostHog API error: ${status}`);
    this.name = "PostHogError";
  }
}
const percentage = (n: number, total: number) =>
  total ? Math.round((n / total) * 10000) / 100 : 0;

async function queryRows(query: string): Promise<unknown[][]> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    ""
  );
  if (!apiKey || !projectId)
    throw new Error("PostHog credentials not configured");
  let response!: Response;
  for (let attempt = 1; attempt <= 3; attempt++) {
    response = await fetch(`${host}/api/projects/${projectId}/query/`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        query: { kind: "HogQLQuery", query: withRowLimit(query) },
      }),
    });
    if (
      response.ok ||
      ![429, 502, 503, 504].includes(response.status) ||
      attempt === 3
    )
      break;
    await new Promise((resolve) =>
      setTimeout(resolve, 1000 * attempt + Math.floor(Math.random() * 250))
    );
  }
  if (!response.ok) throw new PostHogError(response.status);
  const raw = await response.json();
  if (!Array.isArray(raw.results)) throw new Error("Invalid PostHog results");
  return raw.results;
}

function firstRun(rows: unknown[][]) {
  const byEvent = new Map<string, Set<string>>();
  for (const [actor, event] of rows) {
    if (typeof actor !== "string" || typeof event !== "string") continue;
    const users = byEvent.get(event) ?? new Set<string>();
    users.add(actor);
    byEvent.set(event, users);
  }
  // Entrants without a step must remain in the denominator. They arrive via
  // a dedicated entry row in the query (see query union below).
  const totalUsers = byEvent.get("Product Journey Started")?.size ?? 0;
  return {
    totalUsers,
    steps: MOBILE_STEPS.map((s) => ({
      ...s,
      users: byEvent.get(s.event)?.size ?? 0,
      completionRate: percentage(byEvent.get(s.event)?.size ?? 0, totalUsers),
    })),
    methodology:
      "Coarse mobile completion funnel: distinct persons (COALESCE(person_id, distinct_id)) starting the onboarding product journey in the selected window. Steps fire on leave, not view; counts are independent per step, ordered by the wizard. Auth/consent include returning sign-ins; saved speech and flag-gated Setup do not gate later counts. No claim of first-ever onboarding or per-step drop-off.",
  };
}

function tutorial(rows: unknown[][]) {
  const entrants = new Set<string>();
  const steps = ["started", ...TUTORIAL_STEPS, "completed"];
  const users = steps.map(() => new Set<string>());
  const abandoned = Array.from({ length: 6 }, () => new Set<string>());
  const priority = (row: unknown[]) =>
    row[1] === "Device Onboarding Started"
      ? 0
      : row[1] === "Device Onboarding Step Completed"
      ? 1 + TUTORIAL_STEPS.indexOf(String(row[2]))
      : 20;
  const sorted = [...rows].sort(
    (a, b) =>
      String(a[0]).localeCompare(String(b[0])) ||
      Date.parse(String(a[4])) - Date.parse(String(b[4])) ||
      priority(a) - priority(b)
  );
  let actor = "",
    auto = false;
  let completedSteps = new Set<string>();
  for (const [id, event, step, source] of sorted) {
    if (typeof id !== "string") continue;
    if (id !== actor) {
      actor = id;
      auto = false;
    }
    if (event === "Device Onboarding Started") {
      auto = source === "auto";
      completedSteps = new Set();
      if (auto) {
        entrants.add(id);
        users[0].add(id);
      }
      continue;
    }
    if (!auto) continue;
    if (
      event === "Device Onboarding Step Completed" &&
      TUTORIAL_STEPS.includes(String(step))
    ) {
      completedSteps.add(String(step));
      for (let i = 0; i < TUTORIAL_STEPS.length; i++) {
        if (!completedSteps.has(TUTORIAL_STEPS[i])) break;
        users[i + 1].add(id);
      }
    }
    if (event === "Device Onboarding Completed") {
      if (TUTORIAL_STEPS.every((s) => completedSteps.has(s)))
        users[users.length - 1].add(id);
      auto = false;
    }
    if (event === "Device Onboarding Abandoned") {
      const index = Number(step);
      if (
        String(step) !== "" &&
        Number.isInteger(index) &&
        index >= 0 &&
        index < 6
      )
        abandoned[index].add(id);
      auto = false;
    }
  }
  return {
    totalUsers: entrants.size,
    steps: steps.map((key, i) => ({
      key,
      users: users[i].size,
      completionRate: percentage(users[i].size, entrants.size),
    })),
    abandonment: abandoned.map((set, step) => ({ step, users: set.size })),
    methodology:
      "CV1 tutorial completion funnel, not pairing or screen views. Distinct persons with Started source=auto in the window; each start is bounded by the next start or terminal. Sequential step credit within that attempt; settings attempts excluded even though only Started carries source. Abandonment is distinct persons per step (not mutually exclusive); step 0 mixes intro skip and transcription abandon. Process kills may emit nothing; no correlation ID exists and same-timestamp ordering is approximate.",
  };
}

function attach(rows: unknown[][]) {
  const actors = new Map<string, { age: number; delay: number }>();
  for (const [id, age, delay] of rows)
    if (typeof id === "string")
      actors.set(id, { age: Number(age), delay: Number(delay) });
  return {
    totalUsers: actors.size,
    windows: [7, 30].map((days) => {
      const seconds = days * 86400;
      const all = Array.from(actors.values());
      const attached = (a: { delay: number }) =>
        a.delay > 0 && a.delay <= seconds;
      const mature = all.filter((a) => a.age >= seconds);
      return {
        days,
        attachedUsers: all.filter(attached).length,
        attachRate: percentage(all.filter(attached).length, all.length),
        matureUsers: mature.length,
        matureAttachedUsers: mature.filter(attached).length,
        matureAttachRate: percentage(
          mature.filter(attached).length,
          mature.length
        ),
      };
    }),
    description:
      "Pendant attach after mobile onboarding — pending volume check for Device Paired.hardware_family=omi_cv1.",
    methodology:
      "Distinct mobile persons completing Onboarding Completed inside the window; earliest completion in that window, then earliest later Device Paired hardware_family=omi_cv1 within 7d / 30d. Uses event timestamps, never reinstall-sensitive person first_paired_at. All-completer rates include immature cohorts; mature rates include only people with the full observation window. Not a choice made inside the wizard; pre-event versions and opted-out users are invisible.",
  };
}

export async function computeMobileOnboarding(
  kind: MobileOnboardingKind,
  days: number
) {
  if (!Number.isInteger(days) || days < 1 || days > 365)
    throw new Error("days must be an integer from 1 to 365");
  const query =
    kind === "first-run"
      ? firstRunQuery(days)
      : kind === "tutorial"
      ? tutorialQuery(days)
      : attachQuery(days);
  const rows = await queryRows(query);
  const payload =
    kind === "first-run"
      ? firstRun(rows)
      : kind === "tutorial"
      ? tutorial(rows)
      : attach(rows);
  return {
    days,
    ...payload,
    truncated: rows.length >= POSTHOG_SERVED_MAX_ROWS,
  };
}
