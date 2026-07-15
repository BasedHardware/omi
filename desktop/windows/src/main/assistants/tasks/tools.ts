// The TaskAssistant's Gemini tool declarations — the 5 native function-calling
// tools the single-phase extraction loop drives, ending in `extract_task`.
// Ported 1:1 from Mac's `GeminiTool(functionDeclarations: [...])`
// (TaskAssistant.swift:963–1038): every name, type, enum value, and description
// string below is verbatim.
//
// TYPES ARE REUSED from `insight/models.ts` (the same wire shapes the tool loop
// serializes), via indexed access — NOT re-declared. insight's tools never used
// an array parameter, so its `PropertySpec` has no `items`; `extract_task.tags`
// is Gemini's one array field, which the protocol requires to carry an `items`
// sub-spec. So the task property type is insight's exact shape widened with an
// optional `items` — an additive superset, still structurally assignable back to
// insight's `GeminiTool` for the shared wire layer.
import type { GeminiTool } from '../insight/models'

type InsightFunctionDeclaration = GeminiTool['function_declarations'][number]
type InsightPropertySpec = InsightFunctionDeclaration['parameters']['properties'][string]

/** insight's `PropertySpec` + the `items` sub-spec Gemini requires on an array
 *  parameter (`extract_task.tags`). Every non-array field is unchanged. */
export type TaskPropertySpec = InsightPropertySpec & { items?: { type: string } }

export type TaskFunctionDeclaration = {
  name: string
  description: string
  parameters: {
    type: 'object'
    properties: Record<string, TaskPropertySpec>
    required: string[]
  }
}

/** One Gemini `tool` carrying all 5 task declarations (Mac wraps them in a single
 *  `GeminiTool`). Assignable to insight's `GeminiTool` for the shared wire loop. */
export type TaskGeminiTool = { function_declarations: TaskFunctionDeclaration[] }

export const TASK_TOOLS: TaskGeminiTool = {
  function_declarations: [
    {
      name: 'search_similar',
      description:
        'Search for semantically similar existing tasks using vector similarity. Call this when you see a potential request and want to check for duplicates.',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'A concise description of the potential task to search for'
          }
        },
        required: ['query']
      }
    },
    {
      name: 'search_keywords',
      description:
        'Search for existing tasks matching specific keywords. Use this for precise keyword-based matching complementing vector search.',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: 'Keywords to search for in existing tasks'
          }
        },
        required: ['query']
      }
    },
    {
      name: 'no_task_found',
      description:
        'Call this when there is no actionable request on screen. This is the most common outcome (~90% of screenshots). Use for: code editors, terminals, settings, media players, dashboards, or any screen without a direct request from another person or AI.',
      parameters: {
        type: 'object',
        properties: {
          context_summary: {
            type: 'string',
            description: 'Brief summary of what the user is looking at'
          },
          current_activity: {
            type: 'string',
            description: 'What the user is actively doing'
          }
        },
        required: ['context_summary', 'current_activity']
      }
    },
    {
      name: 'extract_task',
      description:
        'Emit canonical capture facts for a new task, enrichment, update, or completion. Call ONLY after searching. All fields are required.',
      parameters: {
        type: 'object',
        properties: {
          title: {
            type: 'string',
            description:
              "Verb-first task title, 6–15 words. MUST name a specific person/project/artifact and a concrete action. If you can't write 6+ specific words, call no_task_found instead."
          },
          description: {
            type: 'string',
            description: 'Additional context about the task. Empty string if none.'
          },
          priority: {
            type: 'string',
            description: 'Task priority',
            enum: ['high', 'medium', 'low']
          },
          tags: {
            type: 'array',
            description: '1-3 relevant tags',
            items: { type: 'string' }
          },
          source_app: {
            type: 'string',
            description: 'App where the task was found'
          },
          inferred_deadline: {
            type: 'string',
            description:
              "Deadline in yyyy-MM-dd format (e.g. '2025-10-04'). Resolve relative references like 'Thursday' or 'next week' to an actual date. Empty string if no deadline."
          },
          confidence: {
            type: 'number',
            description: 'Confidence score 0.0-1.0'
          },
          context_summary: {
            type: 'string',
            description: 'Brief summary of what user is looking at'
          },
          current_activity: {
            type: 'string',
            description: 'What the user is actively doing'
          },
          source_category: {
            type: 'string',
            description: 'Where the task originated',
            enum: [
              'direct_request',
              'self_generated',
              'calendar_driven',
              'reactive',
              'external_system',
              'other'
            ]
          },
          source_subcategory: {
            type: 'string',
            description: 'Specific origin within category',
            enum: [
              'message',
              'meeting',
              'mention',
              'commitment',
              'idea',
              'reminder',
              'goal_subtask',
              'event_prep',
              'recurring',
              'deadline',
              'error',
              'notification',
              'observation',
              'project_tool',
              'alert',
              'documentation',
              'other'
            ]
          },
          capture_kind: {
            type: 'string',
            description: 'Shared capture-policy fact',
            enum: [
              'explicit_command',
              'clear_commitment',
              'direct_request',
              'inferred_next_step',
              'already_done'
            ]
          },
          owner: {
            type: 'string',
            description: 'Who owns the action',
            enum: ['user', 'other', 'unknown']
          },
          concrete_deliverable: {
            type: 'boolean',
            description: 'Whether the action has a concrete deliverable'
          },
          public_broadcast: {
            type: 'boolean',
            description: 'True for an unowned public-channel request'
          },
          direct_mention: {
            type: 'boolean',
            description: 'True when the user was directly mentioned'
          },
          duplicate_of: {
            type: 'string',
            description: 'Existing canonical task id when duplicate; empty otherwise'
          },
          refines_task: {
            type: 'string',
            description: 'Existing canonical task id when this refines it; empty otherwise'
          },
          ownership_confidence: {
            type: 'number',
            description: 'Owner confidence 0.0-1.0'
          }
        },
        required: [
          'title',
          'description',
          'priority',
          'tags',
          'source_app',
          'inferred_deadline',
          'confidence',
          'context_summary',
          'current_activity',
          'source_category',
          'source_subcategory',
          'capture_kind',
          'owner',
          'concrete_deliverable',
          'public_broadcast',
          'direct_mention',
          'duplicate_of',
          'refines_task',
          'ownership_confidence'
        ]
      }
    },
    {
      name: 'reject_task',
      description:
        'Reject only a previously rejected/deleted item or a no-op with no useful new evidence. Active duplicates, refinements, and newly observed completion must use extract_task.',
      parameters: {
        type: 'object',
        properties: {
          reason: {
            type: 'string',
            description:
              "Why this task was rejected (e.g. 'duplicate of existing active task', 'already completed')"
          },
          context_summary: {
            type: 'string',
            description: 'Brief summary of what user is looking at'
          },
          current_activity: {
            type: 'string',
            description: 'What the user is actively doing'
          }
        },
        required: ['reason', 'context_summary', 'current_activity']
      }
    }
  ]
}
