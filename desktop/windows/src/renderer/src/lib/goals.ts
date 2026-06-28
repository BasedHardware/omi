// Goal helpers for the onboarding "Pick one goal" step.
//
// Two pure helpers (prompt builder + target-value parser) are exported for unit
// testing; the network-touching pieces (`generateGoal`, `createGoal`) wrap them
// with the agent LLM and the Omi goals API respectively.
import { omiApi } from './apiClient'
import { callAgentLLM } from './agentLLM'

// Build the single-shot prompt that asks the agent to propose ONE measurable
// goal. When we know which apps the user works with (from the onboarding brain
// map) we feed them in so the suggestion is personal; otherwise we ask for a
// generic productivity goal.
export function buildGoalPrompt(apps: string[]): string {
  const cleaned = apps.map((a) => a.trim()).filter(Boolean)
  const context = cleaned.length
    ? `I work with these apps and tools: ${cleaned.join(', ')}. `
    : ''
  return (
    `${context}Suggest ONE specific personal-productivity goal tailored to me. ` +
    `It must be a single sentence and contain a measurable number so progress ` +
    `can be tracked. Reply with ONLY the goal sentence — no preamble, quotes, or ` +
    `explanation.`
  )
}

// Pull the first number out of a goal sentence to use as the backend's required
// target_value (e.g. "Ship 2 features per week" → 2). The backend 422s without
// one, so we default to 1 (a boolean-style goal) when the text has no number —
// matching the fallback the goals dashboard uses for its suggestions.
export function parseTargetValue(text: string): number {
  const match = text.replace(/,/g, '').match(/\d+(\.\d+)?/)
  if (!match) return 1
  const value = Number(match[0])
  return Number.isFinite(value) && value > 0 ? value : 1
}

// Ask the agent LLM for a tailored goal. Returns a trimmed single line (the
// model occasionally wraps the answer in quotes or adds a trailing period-less
// fragment; we strip surrounding quotes and collapse whitespace).
export async function generateGoal(apps: string[]): Promise<string> {
  const raw = await callAgentLLM(buildGoalPrompt(apps))
  return raw
    .trim()
    .replace(/^["'`]+|["'`]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Best-effort: persist the chosen goal to the Omi backend so it shows up in the
// goals dashboard. target_value is REQUIRED by POST /v1/goals (it 422s without
// one), so we derive it from the goal text. Callers should treat failure as
// non-fatal — onboarding must not block on the network.
export async function createGoal(title: string): Promise<void> {
  await omiApi.post('/v1/goals', { title, target_value: parseTargetValue(title) })
}
