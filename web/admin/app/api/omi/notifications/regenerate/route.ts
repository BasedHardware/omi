import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import OpenAI from 'openai';

export const dynamic = 'force-dynamic';

const BATCH_SIZE = 5;

interface RegenerateItem {
  current_conversation: string;
  recent_notifications: string;
  past_conversations: string;
  original_notification_text?: string;
}

interface RegenerateRequest {
  prompt_template: string;
  user_name: string;
  user_facts: string;
  goals_text: string;
  frequency: number;
  items: RegenerateItem[];
}

const FREQUENCY_GUIDANCE: Record<number, string> = {
  1: 'Ultra selective. Only prevent clear mistakes or truly critical insights. 1-3 per day max.',
  2: 'Very selective. Only non-obvious insights tied to specific goals or history. 3-5 per day.',
  3: 'Balanced. Only when you have a specific, actionable insight the user would miss. 5-8 per day.',
  4: 'Proactive. Share specific insights connecting this conversation to goals/history. 8-12 per day.',
  5: 'Very proactive. Share insights when you spot non-obvious connections. Up to 12 per day.',
};

// ---------------------------------------------------------------------------
// JSON Schemas
// ---------------------------------------------------------------------------

const GATE_SCHEMA = {
  type: 'object' as const,
  additionalProperties: false,
  properties: {
    is_relevant: {
      type: 'boolean' as const,
      description: 'True ONLY if there is a specific, concrete insight the user would genuinely benefit from hearing right now. Most conversations are NOT relevant — default to false.',
    },
    relevance_score: {
      type: 'number' as const,
      description: '0.90+: preventing a concrete mistake or time-sensitive opportunity. 0.75-0.89: non-obvious connection. 0.60-0.74: somewhat useful. Below 0.60: not worth interrupting.',
    },
    reasoning: {
      type: 'string' as const,
      description: 'What specific thing in the conversation warrants a notification. Must cite a concrete detail.',
    },
    context_summary: {
      type: 'string' as const,
      description: 'Brief summary of what user is discussing (1 sentence).',
    },
  },
  required: ['is_relevant', 'relevance_score', 'reasoning', 'context_summary'] as const,
};

const RESULT_SCHEMA = {
  type: 'object' as const,
  properties: {
    has_advice: {
      type: 'boolean' as const,
      description:
        'True ONLY when advice is SPECIFIC to the conversation AND the user likely would NOT figure it out themselves. False in all other cases.',
    },
    advice: {
      anyOf: [
        {
          type: 'object' as const,
          additionalProperties: false,
          properties: {
            notification_text: {
              type: 'string' as const,
              description: 'The advice. Max 100 chars. Start with the actionable part. No filler words.',
            },
            reasoning: {
              type: 'string' as const,
              description:
                'Why this is worth interrupting. MUST name a specific fact, goal, or past conversation. If you cannot, set has_advice=false.',
            },
            confidence: {
              type: 'number' as const,
              description:
                '0.90+: preventing a concrete mistake or critical non-obvious connection. 0.75-0.89: specific dot-connecting across conversations the user would miss. 0.60-0.74: useful but user might figure it out. Below 0.60: do not send.',
            },
            category: {
              type: 'string' as const,
              enum: ['productivity', 'mistake_prevention', 'goal_connection', 'dot_connecting'],
              description: 'One of: productivity, mistake_prevention, goal_connection, dot_connecting',
            },
          },
          required: ['notification_text', 'reasoning', 'confidence', 'category'] as const,
        },
        { type: 'null' as const },
      ],
    },
    context_summary: {
      type: 'string' as const,
      description: 'Brief summary of what user is discussing (1 sentence). Always provided.',
    },
    current_activity: {
      type: ['string', 'null'] as const,
      description: 'What the user is doing or deciding right now.',
    },
  },
  required: ['has_advice', 'advice', 'context_summary', 'current_activity'] as const,
};

const CRITIC_SCHEMA = {
  type: 'object' as const,
  additionalProperties: false,
  properties: {
    approved: {
      type: 'boolean' as const,
      description: 'True ONLY if you would genuinely want to receive this notification yourself. Most should be rejected.',
    },
    reasoning: {
      type: 'string' as const,
      description: 'Why this should or should not be sent to the user\'s phone.',
    },
  },
  required: ['approved', 'reasoning'] as const,
};

// ---------------------------------------------------------------------------
// Gate prompt
// ---------------------------------------------------------------------------

const GATE_PROMPT = `You decide whether {user_name}'s current conversation contains something worth interrupting them about.

IMPORTANT: Most conversations do NOT warrant a notification. Your default answer is is_relevant=false.

{user_name} should be interrupted ONLY when you can point to a SPECIFIC thing:
- {user_name} is about to make a concrete mistake (wrong numbers, contradicting a commitment, agreeing to something bad)
- Someone said something that directly conflicts with {user_name}'s stated plans, commitments, or history
- There is a time-sensitive action {user_name} should take RIGHT NOW that they will miss otherwise
- A specific, non-obvious connection between what's being said and {user_name}'s history that changes their next move

{user_name} should NOT be interrupted for:
- General conversations that loosely relate to their work or goals
- Topics where {user_name} is already handling things correctly
- Conversations where {user_name} is not speaking — unless someone said something critical that demands immediate action
- Anything where you need to stretch to justify relevance
- Opportunities to remind {user_name} about their goals (they already know their goals)
- Topics similar to RECENT NOTIFICATIONS below

== {user_name}'S FACTS ==
{user_facts}

== {user_name}'S GOALS ==
{goals_text}

== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not flag similar topics) ==
{recent_notifications}`;

// ---------------------------------------------------------------------------
// Critic prompt
// ---------------------------------------------------------------------------

const CRITIC_PROMPT = `You are the last gate before this notification hits {user_name}'s phone. Your job is to BLOCK bad notifications. Most notifications should be REJECTED.

NOTIFICATION: "{notification_text}"
REASONING: "{draft_reasoning}"

THE CONVERSATION IT'S BASED ON:
{current_conversation}

{user_name}'S GOALS:
{goals_text}

Imagine you are {user_name}. You're in the middle of a conversation. Your phone buzzes. You look down and see this notification. Do you think:
A) "Oh shit, glad I saw this — this changes what I do next" → APPROVE
B) "I already know this / this is obvious / this is annoying / so what?" → REJECT

REJECT if ANY of these are true:
- The notification tells {user_name} something they clearly already know from the conversation
- The notification is a reminder about goals without providing new information
- The advice could apply to literally anyone in any conversation
- The notification uses vague corporate language (align, prioritize, leverage, ensure, optimize, reassess)
- The notification starts with a goal name (e.g. "30-video goal:", "Meet 12 people goal:")
- Removing this notification from {user_name}'s day would change absolutely nothing
- The "specific reference" in the reasoning is actually a stretch or very generic

APPROVE only if ALL of these are true:
- The notification contains specific information {user_name} genuinely does not have right now
- A smart friend would say this exact thing in person and {user_name} would thank them
- NOT seeing this notification could lead to a missed opportunity or avoidable mistake`;

// ---------------------------------------------------------------------------
// Step 1: Gate
// ---------------------------------------------------------------------------

async function runGate(
  client: OpenAI,
  userName: string,
  userFacts: string,
  goalsText: string,
  item: RegenerateItem,
): Promise<{ is_relevant: boolean; relevance_score: number; reasoning: string; context_summary: string }> {
  const prompt = GATE_PROMPT
    .replace(/{user_name}/g, userName)
    .replace(/{user_facts}/g, userFacts)
    .replace(/{goals_text}/g, goalsText)
    .replace(/{current_conversation}/g, item.current_conversation)
    .replace(/{recent_notifications}/g, item.recent_notifications);

  const response = await client.chat.completions.create({
    model: 'gpt-4.1-mini',
    messages: [{ role: 'user', content: prompt }],
    response_format: {
      type: 'json_schema',
      json_schema: { name: 'gate_result', strict: true, schema: GATE_SCHEMA },
    },
    temperature: 0.3,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) throw new Error('Empty gate response');
  return JSON.parse(content);
}

// ---------------------------------------------------------------------------
// Step 2: Generate (uses the user's prompt template)
// ---------------------------------------------------------------------------

async function runGenerate(
  client: OpenAI,
  promptTemplate: string,
  userName: string,
  userFacts: string,
  goalsText: string,
  frequency: number,
  item: RegenerateItem,
): Promise<any> {
  const frequencyGuidance = FREQUENCY_GUIDANCE[frequency] || FREQUENCY_GUIDANCE[3];

  let prompt = promptTemplate
    .replace(/{user_name}/g, userName)
    .replace(/{user_facts}/g, userFacts)
    .replace(/{goals_text}/g, goalsText)
    .replace(/{current_conversation}/g, item.current_conversation)
    .replace(/{recent_notifications}/g, item.recent_notifications)
    .replace(/{past_conversations}/g, item.past_conversations)
    .replace(/{frequency_guidance}/g, frequencyGuidance);

  if (item.original_notification_text) {
    prompt += `\n\n== ORIGINAL NOTIFICATION (regenerate this) ==\nThis notification was previously sent: "${item.original_notification_text}"\nYou MUST set has_advice=true and regenerate this notification using the rules above. Stay on the SAME topic as the original. Do NOT skip it.`;
  }

  const response = await client.chat.completions.create({
    model: 'gpt-4.1-mini',
    messages: [{ role: 'user', content: prompt }],
    response_format: {
      type: 'json_schema',
      json_schema: { name: 'proactive_notification_result', strict: true, schema: { ...RESULT_SCHEMA, additionalProperties: false } },
    },
    temperature: 0.3,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) throw new Error('Empty generate response');
  return JSON.parse(content);
}

// ---------------------------------------------------------------------------
// Step 3: Critic
// ---------------------------------------------------------------------------

async function runCritic(
  client: OpenAI,
  userName: string,
  goalsText: string,
  notificationText: string,
  draftReasoning: string,
  currentConversation: string,
): Promise<{ approved: boolean; reasoning: string }> {
  const prompt = CRITIC_PROMPT
    .replace(/{user_name}/g, userName)
    .replace(/{notification_text}/g, notificationText)
    .replace(/{draft_reasoning}/g, draftReasoning)
    .replace(/{current_conversation}/g, currentConversation)
    .replace(/{goals_text}/g, goalsText);

  const response = await client.chat.completions.create({
    model: 'gpt-4.1-mini',
    messages: [{ role: 'user', content: prompt }],
    response_format: {
      type: 'json_schema',
      json_schema: { name: 'critic_result', strict: true, schema: CRITIC_SCHEMA },
    },
    temperature: 0.3,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) throw new Error('Empty critic response');
  return JSON.parse(content);
}

// ---------------------------------------------------------------------------
// Full pipeline for one item
// ---------------------------------------------------------------------------

async function processItem(
  client: OpenAI,
  promptTemplate: string,
  userName: string,
  userFacts: string,
  goalsText: string,
  frequency: number,
  item: RegenerateItem,
): Promise<any> {
  // Step 1: Gate
  const gate = await runGate(client, userName, userFacts, goalsText, item);

  // Step 2: Generate (always run so we can show what it would produce)
  const generated = await runGenerate(client, promptTemplate, userName, userFacts, goalsText, frequency, item);

  // Step 3: Critic (only if there's advice to critique)
  let critic: { approved: boolean; reasoning: string } | null = null;
  if (generated.has_advice && generated.advice?.notification_text) {
    critic = await runCritic(
      client,
      userName,
      goalsText,
      generated.advice.notification_text,
      generated.advice.reasoning || '',
      item.current_conversation,
    );
  }

  return {
    ...generated,
    gate: {
      is_relevant: gate.is_relevant,
      relevance_score: gate.relevance_score,
      reasoning: gate.reasoning,
      context_summary: gate.context_summary,
    },
    critic: critic,
  };
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: 'OPENAI_API_KEY not configured' }, { status: 500 });
    }

    const body: RegenerateRequest = await request.json();
    const { prompt_template, user_name, user_facts, goals_text, frequency, items } = body;

    if (!prompt_template || !items || items.length === 0) {
      return NextResponse.json({ error: 'prompt_template and items are required' }, { status: 400 });
    }

    const client = new OpenAI({ apiKey });

    // Process in batches of 5
    const results: any[] = [];
    for (let i = 0; i < items.length; i += BATCH_SIZE) {
      const batch = items.slice(i, i + BATCH_SIZE);
      const batchResults = await Promise.allSettled(
        batch.map((item) => processItem(client, prompt_template, user_name, user_facts, goals_text, frequency, item))
      );
      for (const result of batchResults) {
        if (result.status === 'fulfilled') {
          results.push(result.value);
        } else {
          results.push({ error: result.reason?.message || 'Failed to process', has_advice: false, context_summary: 'Error processing' });
        }
      }
    }

    return NextResponse.json({ results });
  } catch (error: any) {
    console.error('Error regenerating notifications:', error);
    return NextResponse.json(
      { error: `Failed to regenerate: ${error.message}` },
      { status: 500 }
    );
  }
}
