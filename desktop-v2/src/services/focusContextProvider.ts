/**
 * Builds the contextual block injected into every FocusAssistant analysis
 * prompt. Ports Swift's `FocusAssistant.refreshContext()` at
 * `desktop/Desktop/Sources/ProactiveAssistants/Assistants/Focus/FocusAssistant.swift:589-659`.
 *
 * Sections (in order — most important first, so if the prompt is truncated
 * we lose least-critical context):
 *   1. USER PROFILE
 *   2. TIME CONTEXT
 *   3. ACTIVE GOALS        (up to 4)
 *   4. CURRENT TASKS       (up to 5, prioritized)
 *   5. RECENT MEMORIES     (up to 5)
 *
 * Returns `null` when nothing is available so the caller can fall back
 * cleanly (no "CONTEXT:" heading with nothing under it).
 */

import { useGoalStore } from "@/stores/goalStore";
import { useTaskStore } from "@/stores/taskStore";
import { useMemoryStore } from "@/stores/memoryStore";
import { useOnboardingStore } from "@/stores/onboardingStore";

const MAX_GOALS = 4;
const MAX_TASKS = 5;
const MAX_MEMORIES = 5;

function formatTime(): string {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
  return fmt.format(now);
}

export async function buildFocusContext(): Promise<string | null> {
  const sections: string[] = [];

  // 1. User profile.
  const preferredName = useOnboardingStore.getState().preferredName?.trim();
  if (preferredName) {
    sections.push(`USER PROFILE (who this user is):\nName: ${preferredName}`);
  }

  // 2. Time context.
  sections.push(`TIME CONTEXT:\n${formatTime()}`);

  // 3. Active goals.
  const goals = useGoalStore.getState().goals.slice(0, MAX_GOALS);
  if (goals.length > 0) {
    const lines = ["ACTIVE GOALS:"];
    goals.forEach((g, i) => {
      const desc = g.description ? ` - ${g.description}` : "";
      const progress =
        g.target_value > 0
          ? ` (${Math.round(g.current_value)}/${Math.round(g.target_value)}${
              g.unit ? ` ${g.unit}` : ""
            })`
          : "";
      lines.push(`${i + 1}. ${g.title}${desc}${progress}`);
    });
    sections.push(lines.join("\n"));
  }

  // 4. Current tasks — open tasks, prioritized by due date then recency.
  const tasks = useTaskStore
    .getState()
    .tasks.filter((t) => !t.completed)
    .slice(0, MAX_TASKS);
  if (tasks.length > 0) {
    const lines = ["CURRENT TASKS (by importance):"];
    tasks.forEach((t, i) => {
      const due = t.due_at ? ` [due ${t.due_at.slice(0, 10)}]` : "";
      lines.push(`${i + 1}. ${t.description}${due}`);
    });
    sections.push(lines.join("\n"));
  }

  // 5. Recent memories.
  const memories = useMemoryStore.getState().memories.slice(0, MAX_MEMORIES);
  if (memories.length > 0) {
    const lines = ["RECENT MEMORIES:"];
    memories.forEach((m, i) => {
      lines.push(`${i + 1}. ${m.content}`);
    });
    sections.push(lines.join("\n"));
  }

  if (sections.length === 0) return null;
  return sections.join("\n\n");
}
