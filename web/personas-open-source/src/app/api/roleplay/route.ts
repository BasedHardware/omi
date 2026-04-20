import OpenAI from 'openai';
import { NextResponse } from 'next/server';
import {
  buildRoleplayPrompt,
  buildRoleplayScorecardPrompt,
  getRoleplayScenarioById,
  type RoleplayDifficulty,
  type RoleplayGoalCoverage,
  type RoleplayScorecard,
  type RoleplayTranscriptMessage,
} from '@/lib/sales-roleplay';

const ROLEPLAY_MODEL = 'google/gemini-2.5-flash-lite';

const getOpenAIClient = () =>
  new OpenAI({
    baseURL: 'https://openrouter.ai/api/v1',
    apiKey: process.env.OPENROUTER_API_KEY || '',
    defaultHeaders: {
      'X-Title': 'Omi Sales Roleplay',
    },
  });

type RoleplayRequestBody = {
  mode?: 'roleplay' | 'scorecard';
  message?: string;
  scenarioId?: string;
  difficulty?: RoleplayDifficulty;
  repObjective?: string;
  conversationHistory?: RoleplayTranscriptMessage[];
};

const parseJsonContent = (content: string) => {
  const trimmed = content.trim();
  const withoutFences = trimmed
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/\s*```$/i, '');

  return JSON.parse(withoutFences);
};

const toStringList = (value: unknown) =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const withFallbackList = (value: string[], fallback: string[]) =>
  value.length > 0 ? value : fallback;

const normalizeGoalCoverage = (value: unknown, goals: string[]): RoleplayGoalCoverage[] => {
  const parsed = Array.isArray(value) ? value : [];
  const byGoal = new Map<string, RoleplayGoalCoverage>();

  for (const item of parsed) {
    if (!item || typeof item !== 'object') continue;
    const entry = item as Record<string, unknown>;
    const goal = typeof entry.goal === 'string' ? entry.goal : '';
    if (!goal) continue;

    const status =
      entry.status === 'hit' || entry.status === 'partial' || entry.status === 'missed'
        ? entry.status
        : 'missed';
    const evidence = typeof entry.evidence === 'string' ? entry.evidence : '';

    byGoal.set(goal, { goal, status, evidence });
  }

  return goals.map((goal) => {
    const existing = byGoal.get(goal);
    return (
      existing ?? {
        goal,
        status: 'missed',
        evidence: 'No clear evidence captured in the transcript.',
      }
    );
  });
};

const normalizeScorecard = (value: unknown, goals: string[]): RoleplayScorecard => {
  const candidate: Record<string, unknown> =
    value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

  const overallScore =
    typeof candidate.overallScore === 'number'
      ? Math.max(1, Math.min(100, Math.round(candidate.overallScore)))
      : 50;

  return {
    overallScore,
    outcome:
      typeof candidate.outcome === 'string' && candidate.outcome.trim()
        ? candidate.outcome.trim()
        : 'Needs review',
    summary:
      typeof candidate.summary === 'string' && candidate.summary.trim()
        ? candidate.summary.trim()
        : 'The conversation completed, but the coaching summary could not be generated cleanly.',
    strengths: withFallbackList(toStringList(candidate.strengths).slice(0, 4), [
      'The rep kept the conversation moving and stayed engaged with the buyer.',
    ]),
    missedOpportunities: withFallbackList(
      toStringList(candidate.missedOpportunities).slice(0, 4),
      ['The rep should sharpen discovery and make the next step more explicit.'],
    ),
    buyerSignals: withFallbackList(toStringList(candidate.buyerSignals).slice(0, 4), [
      'The buyer did not yet show a strong commitment signal in the transcript.',
    ]),
    nextStepAdvice:
      typeof candidate.nextStepAdvice === 'string' && candidate.nextStepAdvice.trim()
        ? candidate.nextStepAdvice.trim()
        : 'Sharpen discovery and secure a more concrete next step.',
    recommendedNextLine:
      typeof candidate.recommendedNextLine === 'string' && candidate.recommendedNextLine.trim()
        ? candidate.recommendedNextLine.trim()
        : 'Can I confirm the one workflow issue you would want to fix first?',
    goalCoverage: normalizeGoalCoverage(candidate.goalCoverage, goals),
  };
};

export async function POST(req: Request) {
  try {
    if (!process.env.OPENROUTER_API_KEY) {
      return NextResponse.json(
        { message: 'OPENROUTER_API_KEY is not configured for the sales role-play endpoint.' },
        { status: 500 },
      );
    }

    const {
      mode = 'roleplay',
      message,
      scenarioId,
      difficulty,
      repObjective,
      conversationHistory,
    } = (await req.json()) as RoleplayRequestBody;

    if (!scenarioId || !difficulty) {
      return NextResponse.json({ message: 'Missing required params' }, { status: 400 });
    }

    const scenario = getRoleplayScenarioById(scenarioId);
    if (!scenario) {
      return NextResponse.json({ message: 'Scenario not found' }, { status: 404 });
    }

    const systemPrompt = buildRoleplayPrompt({
      scenario,
      difficulty: difficulty as RoleplayDifficulty,
      repObjective,
    });

    const safeConversationHistory = Array.isArray(conversationHistory)
      ? conversationHistory.filter(
          (item): item is RoleplayTranscriptMessage =>
            !!item &&
            (item.sender === 'user' || item.sender === 'omi') &&
            typeof item.text === 'string',
        )
      : [];

    const openai = getOpenAIClient();

    if (mode === 'scorecard') {
      const completion = await openai.chat.completions.create({
        model: ROLEPLAY_MODEL,
        messages: [
          {
            role: 'system',
            content:
              'You are a rigorous sales coach. Return only valid JSON that matches the requested schema.',
          },
          {
            role: 'user',
            content: buildRoleplayScorecardPrompt({
              scenario,
              difficulty: difficulty as RoleplayDifficulty,
              repObjective,
              conversationHistory: safeConversationHistory,
            }),
          },
        ],
        temperature: 0.3,
        max_tokens: 900,
      });

      const content = completion.choices[0]?.message?.content;
      if (!content) {
        return NextResponse.json(
          { message: 'Scorecard generation returned no content.' },
          { status: 502 },
        );
      }

      const parsed = parseJsonContent(content);
      const scorecard = normalizeScorecard(parsed, scenario.goals);

      return NextResponse.json({ scorecard });
    }

    if (!message) {
      return NextResponse.json({ message: 'Missing roleplay message' }, { status: 400 });
    }

    const formattedMessages = [
      { role: 'system' as const, content: systemPrompt },
      ...safeConversationHistory.map((msg) => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text,
      })),
      { role: 'user' as const, content: message },
    ];

    const stream = await openai.chat.completions.create({
      model: ROLEPLAY_MODEL,
      messages: formattedMessages,
      stream: true,
      temperature: 0.9,
      max_tokens: 700,
    });

    const encoder = new TextEncoder();
    const customStream = new ReadableStream({
      async start(controller) {
        try {
          for await (const chunk of stream) {
            const content = chunk.choices[0]?.delta?.content || '';
            if (content) {
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ text: content })}\n\n`),
              );
            }
          }
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        } catch (error) {
          controller.error(error);
        }
      },
    });

    return new Response(customStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (error: any) {
    console.error('Error in roleplay route:', error);

    return NextResponse.json(
      {
        error: 'Failed to get roleplay response',
        details: error.message || 'Unknown error',
      },
      { status: 500 },
    );
  }
}
