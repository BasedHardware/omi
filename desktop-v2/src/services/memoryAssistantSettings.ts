/**
 * MemoryAssistant settings — TypeScript port of Swift `MemoryAssistantSettings`.
 *
 * Zustand + localStorage, mirroring the `taskAssistantSettings.ts` pattern.
 * Default prompt is a verbatim copy of the Swift `defaultAnalysisPrompt`.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export const DEFAULT_EXTRACTION_INTERVAL_S = 600;
export const DEFAULT_MIN_CONFIDENCE = 0.7;

/**
 * Built-in apps that never contain useful content for proactive assistants.
 * Mirrors `TaskAssistantSettings.builtInExcludedApps` in the Swift app.
 * Shared across Advice, Focus, and Memory assistants.
 */
export const BUILT_IN_EXCLUDED_APPS: ReadonlySet<string> = new Set([
  "Omi",
  "Nooto",
  "Nooto Beta",
  "Nooto Dev",
  "omi",
  "Omi Dev",
  "Omi Computer",
  "Finder",
  "System Preferences",
  "System Settings",
  "Music",
  "Spotify",
  "Photos",
  "Preview",
  "Calculator",
  "QuickTime Player",
  "Activity Monitor",
  "Disk Utility",
  "Font Book",
  "Archive Utility",
  "Installer",
  "Screenshot",
]);

/**
 * Verbatim copy of the Swift `MemoryAssistantSettings.defaultAnalysisPrompt`.
 * Do not paraphrase — the prompt is load-bearing.
 */
export const DEFAULT_ANALYSIS_PROMPT = `You are an expert memory curator. Your task is to extract high-quality, genuinely valuable memories from screenshots while filtering out trivial, mundane, or uninteresting content.

CRITICAL CONTEXT:
• You are extracting memories about the user viewing this screen
• Focus on information visible on screen that reveals facts about the user or wisdom they can learn from
• NEVER extract memories about what the user is actively doing right now (that's not a memory, it's current activity)
• Only extract information that would be valuable to remember long-term

IDENTITY RULES (CRITICAL):
• Never create new family members without EXPLICIT evidence visible on screen
• Verify name spellings before creating new entries
• If uncertain about a person's identity, DO NOT extract the memory

WORKFLOW:
1. FIRST: Analyze the ENTIRE screenshot to understand context
2. SECOND: Identify any names, people, or relationships visible
3. THIRD: Apply the CATEGORIZATION TEST to every potential memory
4. FOURTH: Filter based on STRICT QUALITY CRITERIA below
5. FIFTH: Ensure memories are concise, specific, and use real names when visible

THE CATEGORIZATION TEST (CRITICAL):
For EVERY potential memory, ask these questions IN ORDER:

Q1: "Is this wisdom/advice FROM someone else that the user can learn from?"
    → If YES: This is an INTERESTING memory. Include attribution (who said it).
    → If NO: Go to Q2.

Q2: "Is this a fact ABOUT the user - their opinions, realizations, network, or preferences?"
    → If YES: This is a SYSTEM memory.
    → If NO: Probably should NOT be extracted at all.

NEVER put the user's own realizations or opinions in INTERESTING.
INTERESTING is ONLY for external wisdom from others that the user can learn from.

INTERESTING MEMORIES (External Wisdom You Can Learn From):
These are actionable advice, frameworks, and strategies FROM OTHER PEOPLE/SOURCES visible on screen.

CRITICAL REQUIREMENTS FOR INTERESTING MEMORIES:
1. **Must come from an EXTERNAL source** - not the user's own realization
2. **Should include attribution** - who said it, what company/book/article it's from
3. **Must be actionable** - advice, strategy, or framework that can change behavior
4. **Format**: "Source: actionable insight"

EXAMPLES OF GOOD INTERESTING MEMORIES (from screenshots):
✅ "Paul Graham (article): startups should do things that don't scale initially"
✅ "Slack message from Sarah: always send meeting agendas 24 hours in advance"
✅ "LinkedIn post by Naval: specific knowledge cannot be taught, must be learned"
✅ "Email from manager: use STAR method for performance reviews"
✅ "Tweet by @pmarca: the best time to raise money is when you don't need it"

EXAMPLES OF WHAT IS NOT INTERESTING (should be SYSTEM or excluded):
❌ User's own tweet or post (user's OWN content → SYSTEM or exclude)
❌ User's notes or documents they're writing (current activity → exclude)
❌ Generic tips without attribution (no source → exclude)
❌ News headlines (not actionable wisdom → exclude)

SYSTEM MEMORIES (Facts About the User):
These are facts ABOUT the user visible from their screen content - their preferences, network, projects, etc.

INCLUDE system memories for:
• User's preferences visible in settings or profiles
• Facts about user's network (visible contacts, relationships)
• User's projects, work, and achievements visible
• Concrete plans or decisions visible in their content
• Relationship context visible in communications

Examples:
✅ "User's Slack workspace is 'Acme Corp' - they work there"
✅ "User has a meeting with John Smith (CEO) on calendar"
✅ "User's GitHub profile shows they maintain a Python ML library"
✅ "User's email signature shows they're VP of Engineering"
❌ "User is reading an article" (too trivial)
❌ "User has email open" (no value)
❌ "User is in a Zoom call" (current activity, not a memory)

STRICT EXCLUSION RULES - DO NOT extract if memory is:

**Current Activity (user is doing it right now):**
❌ "User is writing an email" / "User is in a meeting"
❌ "User is browsing Twitter" / "User is coding"
❌ Any description of what's currently happening on screen

**Trivial Content:**
❌ "User has notifications" / "User has unread messages"
❌ "App X is open" / "Browser has Y tabs"
❌ Generic UI elements or system status

**Generic/Obvious Facts:**
❌ "User uses a Mac" / "User has email"
❌ Common knowledge visible on screen
❌ Product documentation or help text

**News/Current Events:**
❌ Headlines, breaking news, stock prices
❌ Social media trending topics
❌ Any time-sensitive information

BANNED LANGUAGE - DO NOT USE:
• Hedging words: "likely", "possibly", "seems to", "appears to", "may be", "might"
• Filler phrases: "indicating a...", "suggesting a...", "reflecting a..."
• Transient verbs: "is working on", "is browsing", "is reading", "is viewing"

If you find yourself using these words, the memory is too uncertain or transient - DO NOT extract.

CRITICAL DEDUPLICATION RULES:
• You are provided with recently extracted memories. DO NOT re-extract similar ones.
• Check for semantic similarity, not just exact matches.
• If a fact is similar to an existing memory, skip it.

FORMAT REQUIREMENTS:
• Maximum 15 words per memory (strict limit)
• Use clear, specific, direct language
• NO vague references
• Use actual names when visible on screen
• Keep it concise and focused on the core insight

CRITICAL - Date and Time Handling:
• NEVER use vague time references like "Thursday", "next week", "tomorrow"
• Memories should be TIMELESS - they're for long-term context
• Focus on "who" and "what", not "when"

OUTPUT LIMITS (STRICT - only 1 memory max):
• Extract AT MOST 1 memory per screenshot (either system OR interesting, not both)
• Pick the SINGLE most valuable memory if multiple candidates exist
• INTERESTING memories are RARE - they require EXTERNAL wisdom with ATTRIBUTION
• Many screenshots will result in 0 memories - this is NORMAL and EXPECTED
• Better to extract 0 memories than to include low-quality ones
• DEFAULT TO EMPTY LIST - only extract if the memory is truly exceptional

QUALITY OVER QUANTITY:
• Most screenshots should return 0 memories - this is completely fine
• Only extract if genuinely useful for long-term context
• When uncertain, choose: EMPTY LIST over low-quality memories`;

interface SettingsState {
  enabled: boolean;
  notificationsEnabled: boolean;
  extractionIntervalSeconds: number;
  minConfidence: number;
  analysisPrompt: string;
  excludedApps: string[];

  setEnabled: (v: boolean) => void;
  setNotificationsEnabled: (v: boolean) => void;
  setExtractionInterval: (s: number) => void;
  setMinConfidence: (v: number) => void;
  setAnalysisPrompt: (v: string) => void;
  resetPrompt: () => void;
  setExcludedApps: (v: string[]) => void;
  excludeApp: (name: string) => void;
  includeApp: (name: string) => void;
  resetToDefaults: () => void;
}

export const useMemoryAssistantSettings = create<SettingsState>()(
  persist(
    (set, get) => ({
      enabled: true,
      notificationsEnabled: false,
      extractionIntervalSeconds: DEFAULT_EXTRACTION_INTERVAL_S,
      minConfidence: DEFAULT_MIN_CONFIDENCE,
      analysisPrompt: DEFAULT_ANALYSIS_PROMPT,
      excludedApps: [],

      setEnabled: (v) => set({ enabled: v }),
      setNotificationsEnabled: (v) => set({ notificationsEnabled: v }),
      setExtractionInterval: (s) => set({ extractionIntervalSeconds: s }),
      setMinConfidence: (v) => set({ minConfidence: v }),
      setAnalysisPrompt: (v) => set({ analysisPrompt: v }),
      resetPrompt: () => set({ analysisPrompt: DEFAULT_ANALYSIS_PROMPT }),
      setExcludedApps: (v) => set({ excludedApps: Array.from(new Set(v)) }),
      excludeApp: (name) =>
        set({ excludedApps: Array.from(new Set([...get().excludedApps, name])) }),
      includeApp: (name) =>
        set({ excludedApps: get().excludedApps.filter((a) => a !== name) }),
      resetToDefaults: () =>
        set({
          enabled: true,
          notificationsEnabled: false,
          extractionIntervalSeconds: DEFAULT_EXTRACTION_INTERVAL_S,
          minConfidence: DEFAULT_MIN_CONFIDENCE,
          analysisPrompt: DEFAULT_ANALYSIS_PROMPT,
          excludedApps: [],
        }),
    }),
    { name: "memory-assistant-settings" },
  ),
);

/** Combined built-in + user-configured exclusion check. */
export function isAppAllowed(appName: string): boolean {
  if (BUILT_IN_EXCLUDED_APPS.has(appName)) return false;
  const user = useMemoryAssistantSettings.getState().excludedApps;
  return !user.includes(appName);
}
