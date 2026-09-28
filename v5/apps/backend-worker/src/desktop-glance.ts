// Desktop home-screen "at a glance": POST /v1/desktop/glance. Receives light
// client context (frontmost app, counts, recent topics), optionally enriches
// with current weather (Open-Meteo, no API key, no location persistence) and
// public front-page headlines (HN Algolia, no API key, nothing user-specific
// sent, never logged), and asks the pinned LLM gateway for one short kicker.
// Always returns usable {title, copy}: deterministic local composition is the
// fallback whenever the gateway is absent, misconfigured, or returns anything
// unparseable. Location never reaches logs or storage.

import { gatewayConfig, gatewayReady, generateViaGateway } from "./openrouter";
import { readBoundedJson, type CoreContext } from "./http-core";
import { backendError, json, withTimeout } from "./wire";

const GLANCE_REQUEST_MAX_BYTES = 16_384;
const MAX_STRING_LENGTH = 120;
const MAX_COUNT = 100_000;
const TITLE_MAX = 24;
const COPY_MAX = 140;
const WEATHER_TIMEOUT_MS = 4_000;
const HEADLINE_TIMEOUT_MS = 4_000;
const TOPIC_MAX = 80;
const TOPIC_MAX_COUNT = 8;
const HEADLINE_MAX = 120;
const HEADLINE_MAX_COUNT = 6;

export type GlanceCounts = {
  conversations: number;
  memories: number;
  tasks: number;
};

export type GlanceInput = {
  frontApp: string | null;
  windowTitle: string | null;
  counts: GlanceCounts;
  topics: string[];
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
  'You are Omi\'s home-screen glance. Reply with ONLY compact JSON {"title":string,"copy":string}. title: max 4 words, no emoji, no punctuation. copy: one sentence, max 24 words, warm and specific. If the device context shows something that deserves attention, say that. Otherwise be fun: share a true, well-known fun fact (optionally tied to their recent topics, time of day, or weather) or tease the one candidate headline they would most enjoy. Never invent news or weather; never mention being an AI or a model.';

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
  const rawTopics = record["topics"];
  const topics = Array.isArray(rawTopics)
    ? rawTopics
        .filter((topic): topic is string => typeof topic === "string")
        .filter((topic) => topic.trim().length > 0)
        .map((topic) => clampString(topic, TOPIC_MAX)!)
        .slice(0, TOPIC_MAX_COUNT)
    : [];
  return {
    frontApp: clampString(record["frontApp"]),
    windowTitle: clampString(record["windowTitle"]),
    counts: {
      conversations: clampCount(countsRecord["conversations"]),
      memories: clampCount(countsRecord["memories"]),
      tasks: clampCount(countsRecord["tasks"]),
    },
    topics,
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

// Hacker News Algolia front page: keyless, nothing user-specific is sent,
// and neither the request nor the titles are ever logged. Headlines only
// feed the glance prompt; any failure or timeout just means no enrichment.
export const parseGlanceHeadlines = (body: unknown): string[] => {
  if (body === null || typeof body !== "object") return [];
  const hits = (body as Record<string, unknown>)["hits"];
  if (!Array.isArray(hits)) return [];
  const titles: string[] = [];
  for (const hit of hits) {
    if (hit === null || typeof hit !== "object") continue;
    const title = (hit as Record<string, unknown>)["title"];
    if (typeof title !== "string" || title.trim().length === 0) continue;
    titles.push(clampString(title, HEADLINE_MAX)!);
    if (titles.length >= HEADLINE_MAX_COUNT) break;
  }
  return titles;
};

export const fetchGlanceHeadlines = async (): Promise<string[]> => {
  try {
    return await withTimeout(HEADLINE_TIMEOUT_MS, async (signal) => {
      const response = await fetch(
        "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=6",
        { signal, redirect: "manual" }
      );
      if (!response.ok) return [];
      return parseGlanceHeadlines(await response.json());
    });
  } catch {
    return [];
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

// Verifiable, evergreen fun facts for the no-context fallback. The glance is
// never filler: with nothing live to report, it is at least genuinely fun.
// Rotation is deterministic by minute so repeated opens do not repeat a line.
const FUN_FACTS: readonly { title: string; copy: string }[] = [
  {
    title: "Three hearts",
    copy: "An octopus has three hearts, and two of them stop beating whenever it swims.",
  },
  {
    title: "Eternal honey",
    copy: "Honey found in ancient Egyptian tombs is still considered safe to eat after thousands of years.",
  },
  {
    title: "Berry confusion",
    copy: "Bananas count as berries, while strawberries famously do not.",
  },
  {
    title: "Growing tower",
    copy: "The Eiffel Tower grows roughly 15 centimeters taller on hot days as its iron expands.",
  },
  {
    title: "Wombat geometry",
    copy: "Wombats are the only known animals that produce cube-shaped droppings.",
  },
  {
    title: "Older than trees",
    copy: "Sharks were already swimming the oceans before trees existed.",
  },
  {
    title: "Venus days",
    copy: "A single day on Venus stretches on longer than its whole year around the Sun.",
  },
  {
    title: "Flamboyance",
    copy: "A group of flamingos is called a flamboyance.",
  },
  {
    title: "Otter handholding",
    copy: "Sea otters hold hands while they sleep so they do not drift apart.",
  },
  {
    title: "Scotland's unicorn",
    copy: "The unicorn is the official national animal of Scotland.",
  },
  {
    title: "Shortest war",
    copy: "The Anglo-Zanzibar War of 1896 lasted around 38 minutes, the shortest war on record.",
  },
  {
    title: "Cleopatra's timeline",
    copy: "Cleopatra lived closer in time to the Moon landing than to the Great Pyramid's construction.",
  },
  {
    title: "Older than Aztecs",
    copy: "Oxford University is about three centuries older than the Aztec Empire.",
  },
  {
    title: "Sleepy sloths",
    copy: "Sloths can hold their breath underwater longer than dolphins can.",
  },
  {
    title: "Hungry brain",
    copy: "Your brain is about 2 percent of your body weight yet uses roughly 20 percent of its energy.",
  },
  {
    title: "Densest spoonful",
    copy: "One teaspoon of neutron star material would weigh about a billion tonnes on Earth.",
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
  const fact = FUN_FACTS[minutes % FUN_FACTS.length]!;
  return { title: fact.title, copy: fact.copy, source: "local" };
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
  weather: GlanceWeather | null,
  headlines: string[]
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
  if (input.topics.length > 0) {
    parts.push(`recent topics: ${input.topics.join(", ")}`);
  }
  if (headlines.length > 0) {
    parts.push(`candidate headlines: ${headlines.join(" | ")}`);
  }
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
  const [weather, headlines] = await Promise.all([
    latitude !== null && longitude !== null
      ? fetchGlanceWeather(latitude, longitude)
      : Promise.resolve(null),
    fetchGlanceHeadlines(),
  ]);

  if (gatewayReady(context.env)) {
    const config = gatewayConfig(context.env);
    if (config !== null) {
      const result = await generateViaGateway(
        config,
        `Device context: ${contextSummary(input, weather, headlines)}`,
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
