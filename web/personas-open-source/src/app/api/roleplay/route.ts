import OpenAI from 'openai';
import { NextResponse } from 'next/server';
import {
  buildRoleplayPrompt,
  getRoleplayScenarioById,
  type RoleplayDifficulty,
} from '@/lib/sales-roleplay';

const getOpenAIClient = () =>
  new OpenAI({
    baseURL: 'https://openrouter.ai/api/v1',
    apiKey: process.env.OPENROUTER_API_KEY || '',
    defaultHeaders: {
      'X-Title': 'Omi Sales Roleplay',
    },
  });

export async function POST(req: Request) {
  try {
    const {
      message,
      scenarioId,
      difficulty,
      repObjective,
      conversationHistory,
    } = await req.json();

    if (!message || !scenarioId || !difficulty) {
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

    const formattedMessages = [
      { role: 'system' as const, content: systemPrompt },
      ...((conversationHistory || []).map((msg: { sender: string; text: string }) => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text,
      })) || []),
      { role: 'user' as const, content: message },
    ];

    const openai = getOpenAIClient();
    const stream = await openai.chat.completions.create({
      model: 'google/gemini-2.5-flash-lite',
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
