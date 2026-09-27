// Desktop home-screen "at a glance": POST /v1/desktop/glance. Receives light
// client context, optionally enriches with current weather (Open-Meteo, no
// API key, no location persistence), and asks the pinned LLM gateway for one
// short kicker. Always returns usable {title, copy}: deterministic local
// composition is the fallback whenever the gateway is absent, misconfigured,
// or returns anything unparseable. Location never reaches logs or storage.

import { gatewayConfig, gatewayReady, generateViaGateway } from "./openrouter";
import { readBoundedJson, type CoreContext } from "./http-core";
import { backendError, json, withTimeout } from "./wire";

const GLANCE_REQUEST_MAX_BYTES = 16_384;
const MAX_STRING_LENGTH = 120;
const MAX_COUNT = 100_000;
const TITLE_MAX = 24;
const COPY_MAX = 140;
const WEATHER_TIMEOUT_MS = 4_000;

export type GlanceCounts = {
  conversations: number;
  memories: number;
  tasks: number;
};

export type GlanceInput = {
  frontApp: string | null;
  windowTitle: string | null;
  counts: GlanceCounts;
  localTimeIso: string | null;
};

export type GlanceWeather = {
  temperatureC: number;
  condition: string;
};

export type GlanceResult = {
  title: string;
  copy: string;
  source: "llm" | "local";
};

export const GLANCE_SYSTEM_PROMPT =
  'You are Omi\'s home-screen glance. Given device context, reply with ONLY compact JSON {"title":string,"copy":string}. title: max 4 words, no emoji, no ending punctuation. copy: one sentence, max 24 words, warm, specific, references the given context (frontmost app/window, weather, counts, or time of day); never invent facts beyond the context; never mention being an AI or a model.';

export const clampString = (value: unknown, maxLength = MAX_STRING_LENGTH) =>
  typeof value === "string"
    ? value.length > maxLength
      ? value.slice(0, maxLength)
      : value
    : null;

export const clampCount = (value: unknown): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  if (value <= 0) return 0;
  return Math.min(Math.trunc(value), MAX_COUNT);
};

export const parseGlanceInput = (body: unknown): GlanceInput => {
  const record =
    body !== null && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : {};
  const rawCounts = record["counts"];
  const countsRecord =
    rawCounts !== null &&
    typeof rawCounts === "object" &&
    !Array.isArray(rawCounts)
      ? (rawCounts as Record<string, unknown>)
      : {};
  const rawLocalTime = record["localTimeIso"];
  const localTimeIso =
    typeof rawLocalTime === "string" &&
    !Number.isNaN(new Date(rawLocalTime).getTime())
      ? rawLocalTime
      : null;
  return {
    frontApp: clampString(record["frontApp"]),
    windowTitle: clampString(record["windowTitle"]),
    counts: {
      conversations: clampCount(countsRecord["conversations"]),
      memories: clampCount(countsRecord["memories"]),
      tasks: clampCount(countsRecord["tasks"]),
    },
    localTimeIso,
  };
};

const WMO_CONDITIONS: readonly [readonly number[], string][] = [
  [[0], "clear"],
  [[1, 2, 3], "clouds"],
  [[45, 48], "fog"],
  [[51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82], "rain"],
  [[71, 73, 75, 77, 85, 86], "snow"],
  [[95, 96, 99], "storm"],
];

export const wmoCondition = (code: number): string => {
  for (const [codes, word] of WMO_CONDITIONS) {
    if (codes.includes(code)) return word;
  }
  return "clouds";
};

export const parseGlanceWeather = (body: unknown): GlanceWeather | null => {
  if (body === null || typeof body !== "object") return null;
  const current = (body as Record<string, unknown>)["current"];
  if (current === null || typeof current !== "object") return null;
  const record = current as Record<string, unknown>;
  const temperature = record["temperature_2m"];
  const code = record["weather_code"];
  if (typeof temperature !== "number" || !Number.isFinite(temperature))
    return null;
  if (typeof code !== "number" || !Number.isFinite(code)) return null;
  return {
    temperatureC: Math.round(temperature),
    condition: wmoCondition(code),
  };
};

export const fetchGlanceWeather = async (
  latitude: number,
  longitude: number
): Promise<GlanceWeather | null> => {
  const url =
    "https://api.open-meteo.com/v1/forecast" +
    `?latitude=${encodeURIComponent(String(latitude))}` +
    `&longitude=${encodeURIComponent(String(longitude))}` +
    "&current=temperature_2m,weather_code&timezone=auto";
  try {
    return await withTimeout(WEATHER_TIMEOUT_MS, async (signal) => {
      const response = await fetch(url, { signal, redirect: "manual" });
      if (!response.ok) return null;
      return parseGlanceWeather(await response.json());
    });
  } catch {
    return null;
  }
};

const HOUR_GREETINGS: readonly [number, number, string][] = [
  [5, 11, "Good morning"],
  [12, 16, "Good afternoon"],
  [17, 21, "Good evening"],
  [22, 4, "Late night"],
];

export const timeOfDayGreeting = (localTimeIso: string | null): string => {
  const hour =
    localTimeIso === null
      ? new Date().getHours()
      : new Date(localTimeIso).getHours();
  for (const [from, to, greeting] of HOUR_GREETINGS) {
    if (from <= to ? hour >= from && hour <= to : hour >= from || hour <= to) {
      return greeting;
    }
  }
  return "Hello";
};

const CALM_LINES: readonly { title: string; copy: string }[] = [
  {
    title: "Nothing urgent",
    copy: "The Mac is quiet. A calm moment is still your moment.",
  },
  {
    title: "All clear",
    copy: "No tasks are calling. Breathe and take the next small step.",
  },
  {
    title: "Quiet now",
    copy: "Everything can wait a minute. This one is yours.",
  },
  {
    title: "Steady",
    copy: "Nothing needs you right now. Settle in and ease forward.",
  },
];

export const composeLocalGlance = (
  input: GlanceInput,
  weather: GlanceWeather | null
): GlanceResult => {
  if (weather !== null) {
    return {
      title: clampString(weather.condition, TITLE_MAX)!,
      copy: clampString(
        `${weather.condition}, ${weather.temperatureC}° — ${timeOfDayGreeting(
          input.localTimeIso
        )}`,
        COPY_MAX
      )!,
      source: "local",
    };
  }
  if (input.frontApp !== null) {
    const title = clampString(`Now on ${input.frontApp}`, TITLE_MAX)!;
    const copy =
      input.windowTitle !== null
        ? clampString(input.windowTitle, COPY_MAX)!
        : `${input.frontApp} is front and center.`;
    return { title, copy, source: "local" };
  }
  const minutes =
    input.localTimeIso === null
      ? new Date().getUTCHours() * 60 + new Date().getUTCMinutes()
      : new Date(input.localTimeIso).getUTCHours() * 60 +
        new Date(input.localTimeIso).getUTCMinutes();
  const line = CALM_LINES[minutes % CALM_LINES.length]!;
  return { title: line.title, copy: line.copy, source: "local" };
};

export const parseGlanceLlmText = (text: string): GlanceResult | null => {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text.slice(start, end + 1));
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))
    return null;
  const record = parsed as Record<string, unknown>;
  const title = clampString(record["title"], TITLE_MAX);
  const copy = clampString(record["copy"], COPY_MAX);
  if (
    title === null ||
    title.length === 0 ||
    copy === null ||
    copy.length === 0
  )
    return null;
  return { title, copy, source: "llm" };
};

const contextSummary = (
  input: GlanceInput,
  weather: GlanceWeather | null
): string => {
  const parts: string[] = [];
  if (input.frontApp !== null) {
    parts.push(
      input.windowTitle !== null
        ? `frontmost app: ${input.frontApp} (${input.windowTitle})`
        : `frontmost app: ${input.frontApp}`
    );
  }
  parts.push(
    `counts: ${input.counts.conversations} conversations, ${input.counts.memories} memories, ${input.counts.tasks} tasks`
  );
  if (weather !== null) {
    parts.push(`weather: ${weather.condition}, ${weather.temperatureC}°C`);
  }
  if (input.localTimeIso !== null)
    parts.push(`local time: ${input.localTimeIso}`);
  return parts.join("; ");
};

export async function handleDesktopGlance(
  context: CoreContext
): Promise<Response> {
  const parsed = await readBoundedJson(
    context.req.raw,
    GLANCE_REQUEST_MAX_BYTES
  );
  if (parsed.kind === "too_large" || parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);

  const input = parseGlanceInput(parsed.value);

  const cf = (
    context.req.raw as Request & {
      cf?: { latitude?: unknown; longitude?: unknown };
    }
  ).cf;
  const latitude = typeof cf?.latitude === "number" ? cf.latitude : null;
  const longitude = typeof cf?.longitude === "number" ? cf.longitude : null;
  const weather =
    latitude !== null && longitude !== null
      ? await fetchGlanceWeather(latitude, longitude)
      : null;

  if (gatewayReady(context.env)) {
    const config = gatewayConfig(context.env);
    if (config !== null) {
      const result = await generateViaGateway(
        config,
        `Device context: ${contextSummary(input, weather)}`,
        `glance-${context.get("requestId")}`,
        []
      );
      if (result.kind === "ok") {
        const glance = parseGlanceLlmText(result.text);
        if (glance !== null) return json(glance);
      }
    }
  }

  return json(composeLocalGlance(input, weather));
}
