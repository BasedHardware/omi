/**
 * Keyword → emoji mapping for goals. Ported from Swift `GoalsWidget.swift:375-546`.
 * Case-insensitive substring match against the goal title; first match wins.
 * Falls back to 🎯 if nothing hits.
 */

const TABLE: Array<[string[], string]> = [
  [["revenue", "money", "profit", "income", "sales", "earnings", "$"], "💰"],
  [["startup", "business", "company", "launch"], "🚀"],
  [["user", "customer", "signup", "subscriber"], "👥"],
  [["growth", "scale", "expand"], "📈"],
  [["workout", "gym", "exercise", "fitness", "train"], "💪"],
  [["run", "marathon", "jog", "5k", "10k"], "🏃"],
  [["weight", "lose weight", "pounds", "kilos", "kg", "lb"], "⚖️"],
  [["meditation", "meditate", "mindful", "calm"], "🧘"],
  [["sleep", "rest", "bedtime"], "😴"],
  [["water", "hydrate", "drink"], "💧"],
  [["health", "wellness", "doctor"], "❤️"],
  [["read", "book", "chapter", "novel", "pages"], "📚"],
  [["learn", "study", "course", "class", "lesson"], "🎓"],
  [["code", "coding", "program", "develop", "ship"], "💻"],
  [["language", "spanish", "french", "german", "mandarin", "duolingo"], "🗣️"],
  [["write", "blog", "article", "essay", "word"], "✍️"],
  [["video", "youtube", "film", "record"], "🎥"],
  [["music", "song", "album", "guitar", "piano"], "🎵"],
  [["art", "paint", "draw", "sketch"], "🎨"],
  [["photo", "picture", "camera"], "📷"],
  [["task", "todo", "checklist", "get things done"], "✅"],
  [["habit", "streak", "daily", "routine"], "🔁"],
  [["time", "hour", "minute", "schedule"], "⏰"],
  [["project", "milestone", "deliverable", "ship"], "🏗️"],
  [["travel", "trip", "vacation", "visit"], "✈️"],
  [["home", "clean", "declutter", "organize", "tidy"], "🏠"],
  [["save", "saving", "budget"], "💵"],
  [["social", "network", "meet", "friend"], "🤝"],
  [["family", "kid", "parent"], "👨‍👩‍👧"],
  [["relationship", "partner", "love"], "💖"],
  [["growth", "improve", "better"], "🌱"],
  [["success", "win", "achieve"], "🏆"],
  [["star", "dream"], "⭐"],
  [["eat", "food", "cook", "recipe", "kitchen"], "🍳"],
  [["lawn", "yard", "garden", "grow", "plant"], "🌿"],
  [["car", "drive", "mile"], "🚗"],
  [["pet", "dog", "cat"], "🐾"],
];

export const PRESET_EMOJI: string[] = [
  "🎯", "💰", "🚀", "📈", "💪", "🏃", "🧘", "😴",
  "💧", "❤️", "📚", "🎓", "💻", "✍️", "🎨", "🏆",
  "⭐", "🌱", "✅", "🏠",
];

export function getEmojiForTitle(title: string | undefined | null): string {
  if (!title) return "🎯";
  const lower = title.toLowerCase();
  for (const [keywords, emoji] of TABLE) {
    for (const kw of keywords) {
      if (lower.includes(kw)) return emoji;
    }
  }
  return "🎯";
}
