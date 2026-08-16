// The verbatim Mac goal-generation prompt (GoalPrompts.generateGoal), its system
// instruction, and the Gemini responseSchema for the structured suggestion — a
// 1:1 port so Windows reasons about goals exactly as macOS does.
//
// `fillPrompt` substitutes the seven `{...}` placeholders from a GoalContextData
// bundle (context.ts), applying Mac's empty-state fallbacks so an empty section
// reads as a clear "None"/"No X yet" rather than a blank the model must guess at.
import type { GoalContextData } from './context'

/** Mac's system instruction (GoalsAIService), verbatim. */
export const GOAL_SYSTEM_PROMPT =
  "You are a goal coach. Generate one meaningful, achievable goal based on the user's full context."

/** Mac's GoalPrompts.generateGoal, verbatim. `{...}` placeholders are filled by
 *  `fillPrompt`. Do not reword — the 5-step reasoning is the ported behavior. */
const GOAL_GENERATION_TEMPLATE = `You are generating a personal goal for a user. Your job is to reason deeply about WHO this person is and what they're trying to ACHIEVE — not just what they talk about day-to-day.

STEP 1: Understand the user at a high level. What is their role? What are their ambitions? What life direction are they heading in?

USER'S PERSONA:
{persona_context}

USER'S MEMORIES (facts about them):
{memory_context}

STEP 2: Look at what they're actively working on and talking about. What unmet needs or gaps do you see?

RECENT CONVERSATIONS (what they've been discussing/working on):
{conversation_context}

CURRENT TASKS (each prefixed with [task_id]):
{action_items_context}

STEP 3: Review their goal history. Do NOT re-suggest goals they already completed or abandoned. Learn from what they chose to stop doing.

ACTIVE GOALS (do NOT duplicate):
{existing_goals}

COMPLETED GOALS (already achieved — do not repeat):
{completed_goals}

ABANDONED GOALS (user chose to stop — avoid similar goals unless context strongly suggests they want to retry):
{abandoned_goals}

STEP 4: Synthesize. Based on the above, identify ONE specific, measurable goal that:
1. Reflects what the user is STRIVING for at a deeper level, not just surface-level patterns in their conversations
2. Addresses an unmet need or gap — something they care about but haven't made structured progress on
3. Is NOT a duplicate of any active, completed, or abandoned goal
4. Has a clear numeric target and timeframe implied by the title (e.g., "Ship 3 features this month", "Read 2 books", "Close 5 deals")
5. Would genuinely excite or motivate this specific person

STEP 5: Link relevant tasks. Look at the CURRENT TASKS list above. Pick any tasks (by their [task_id]) that are directly related to achieving this goal. Only link tasks that genuinely contribute to the goal — don't force connections.

Return JSON only:
{
    "suggested_title": "Brief, actionable goal title",
    "suggested_description": "1-2 sentences explaining WHY this goal matters for the user and what achieving it looks like",
    "suggested_type": "scale" or "numeric" or "boolean",
    "suggested_target": <number>,
    "suggested_min": <minimum value>,
    "suggested_max": <maximum value or target>,
    "reasoning": "One sentence explaining why this goal fits the user right now",
    "linked_task_ids": ["task_id_1", "task_id_2"]
}

Choose a goal type:
- "boolean" for yes/no goals (0 or 1)
- "scale" for rating goals (e.g., 0-10 satisfaction)
- "numeric" for countable goals (e.g., books read, money saved, users acquired)`

/** Mac's empty-state fallbacks (GoalsAIService), so a blank section reads clearly. */
const FALLBACKS = {
  persona: 'No persona set',
  memories: 'No memories yet',
  conversations: 'No recent conversations',
  tasks: 'No active tasks',
  goals: 'None'
} as const

/** Fill the generation prompt from an assembled context bundle. Abandoned goals
 *  have no backend signal (Mac's endpoint 404s) → always "None" (never fabricated). */
export function fillPrompt(data: GoalContextData): string {
  const tasks = data.tasks.map((t) => `[${t.id}] ${t.description}`)
  return GOAL_GENERATION_TEMPLATE.replace('{persona_context}', data.persona || FALLBACKS.persona)
    .replace('{memory_context}', data.memories.join('\n') || FALLBACKS.memories)
    .replace('{conversation_context}', data.conversations.join('\n') || FALLBACKS.conversations)
    .replace('{action_items_context}', tasks.join('\n') || FALLBACKS.tasks)
    .replace('{existing_goals}', data.activeGoals.join('\n') || FALLBACKS.goals)
    .replace('{completed_goals}', data.completedGoals.join('\n') || FALLBACKS.goals)
    .replace('{abandoned_goals}', FALLBACKS.goals)
}

/** The Gemini `responseSchema` for the structured suggestion (Mac's
 *  goalSuggestionSchema). `linked_task_ids` is optional — the model may return no
 *  links. The other seven fields are required. */
export const GOAL_SUGGESTION_SCHEMA = {
  type: 'object',
  properties: {
    suggested_title: { type: 'string' },
    suggested_description: { type: 'string' },
    suggested_type: { type: 'string', enum: ['boolean', 'scale', 'numeric'] },
    suggested_target: { type: 'number' },
    suggested_min: { type: 'number' },
    suggested_max: { type: 'number' },
    reasoning: { type: 'string' },
    linked_task_ids: { type: 'array', items: { type: 'string' } }
  },
  required: [
    'suggested_title',
    'suggested_description',
    'suggested_type',
    'suggested_target',
    'suggested_min',
    'suggested_max',
    'reasoning'
  ]
} as const
