import type { Memory } from "../../stores/memoryStore";
import type { ThemeKey } from "./themes";

const KEYWORDS: Record<Exclude<ThemeKey, "other">, string[]> = {
  work: [
    "work",
    "job",
    "boss",
    "colleague",
    "coworker",
    "manager",
    "company",
    "office",
    "project",
    "meeting",
    "deadline",
    "client",
    "career",
    "salary",
    "promoted",
    "hired",
  ],
  people: [
    "wife",
    "husband",
    "partner",
    "girlfriend",
    "boyfriend",
    "friend",
    "friends",
    "mom",
    "dad",
    "mother",
    "father",
    "parent",
    "parents",
    "son",
    "daughter",
    "brother",
    "sister",
    "family",
    "roommate",
  ],
  health: [
    "sleep",
    "sleeping",
    "gym",
    "workout",
    "exercise",
    "run",
    "running",
    "diet",
    "doctor",
    "pain",
    "tired",
    "weight",
    "stress",
    "anxiety",
    "meditation",
    "healthy",
  ],
  interests: [
    "music",
    "song",
    "band",
    "album",
    "book",
    "reading",
    "game",
    "gaming",
    "movie",
    "film",
    "show",
    "hobby",
    "art",
    "painting",
    "cooking",
    "travel",
    "photography",
  ],
  habits: [
    "every",
    "daily",
    "always",
    "usually",
    "morning",
    "evening",
    "night",
    "routine",
    "habit",
    "weekly",
    "often",
    "sometimes",
  ],
  preferences: [
    "likes",
    "loves",
    "prefers",
    "hates",
    "favorite",
    "favourite",
    "dislike",
    "enjoys",
    "doesn't like",
  ],
  plans: [
    "wants to",
    "wants",
    "plans to",
    "planning",
    "will",
    "goal",
    "goals",
    "hoping",
    "hopes",
    "trying to",
    "intends",
    "resolution",
  ],
};

const PRIORITY: Exclude<ThemeKey, "other">[] = [
  "work",
  "people",
  "health",
  "interests",
  "habits",
  "preferences",
  "plans",
];

const escapeRegex = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const PATTERNS: Record<Exclude<ThemeKey, "other">, RegExp> = PRIORITY.reduce(
  (acc, key) => {
    const escaped = KEYWORDS[key].map(escapeRegex).join("|");
    acc[key] = new RegExp(`\\b(${escaped})\\b`, "i");
    return acc;
  },
  {} as Record<Exclude<ThemeKey, "other">, RegExp>,
);

export function classifyByTheme(memories: Memory[]): Record<ThemeKey, Memory[]> {
  const buckets: Record<ThemeKey, Memory[]> = {
    work: [],
    people: [],
    health: [],
    interests: [],
    habits: [],
    preferences: [],
    plans: [],
    other: [],
  };

  for (const memory of memories) {
    const text = memory.content.toLowerCase();
    let matched: ThemeKey = "other";
    for (const key of PRIORITY) {
      if (PATTERNS[key].test(text)) {
        matched = key;
        break;
      }
    }
    buckets[matched].push(memory);
  }

  return buckets;
}
