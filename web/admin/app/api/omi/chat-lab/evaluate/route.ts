import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

interface ClaudeMessage {
  role: 'user' | 'assistant';
  content: string;
}

async function callClaude(system: string, messages: ClaudeMessage[]): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error('ANTHROPIC_API_KEY is not configured');
  }

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 2048,
      system,
      messages,
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Claude API error ${response.status}: ${errorBody}`);
  }

  const data = await response.json();
  const textBlock = data.content?.find((block: { type: string }) => block.type === 'text');
  return textBlock?.text || '';
}

function buildSystemPrompt(promptText: string, floatingPrefix: string): string {
  const now = new Date().toISOString();
  const combined = floatingPrefix ? `${floatingPrefix}\n\n${promptText}` : promptText;

  return combined
    .replace(/\{user_name\}/g, 'Test User')
    .replace(/\{tz\}/g, 'UTC')
    .replace(/\{current_datetime_str\}/g, now);
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { question, prompt_text, floating_prefix, version_id } = body;

    if (!question || !prompt_text) {
      return NextResponse.json({ error: 'question and prompt_text are required' }, { status: 400 });
    }

    const systemPrompt = buildSystemPrompt(prompt_text, floating_prefix || '');

    // First call: generate the response
    const responseText = await callClaude(systemPrompt, [{ role: 'user', content: question }]);

    // Second call: grade the response
    const gradingSystem = `You are an AI response quality grader. Rate responses on a scale of 0-5 based on:
- Relevance to the question (0-1 points)
- Helpfulness and actionability (0-1 points)
- Tone and personality (0-1 points)
- Conciseness — not too long, not too short (0-1 points)
- Overall quality and naturalness (0-1 points)

Respond ONLY with valid JSON in this exact format:
{"score": <number 0-5>, "comment": "<brief explanation>"}`;

    const gradingPrompt = `Question: ${question}\n\nResponse: ${responseText}\n\nRate the response quality 0-5 and provide a brief comment.`;

    const gradingResult = await callClaude(gradingSystem, [{ role: 'user', content: gradingPrompt }]);

    let aiScore = 0;
    let aiComment = '';
    try {
      const parsed = JSON.parse(gradingResult);
      aiScore = parsed.score ?? 0;
      aiComment = parsed.comment ?? '';
    } catch {
      // If grading response isn't valid JSON, extract what we can
      aiComment = gradingResult;
      const scoreMatch = gradingResult.match(/(\d+(?:\.\d+)?)\s*(?:\/\s*5|out of 5)/);
      if (scoreMatch) aiScore = parseFloat(scoreMatch[1]);
    }

    return NextResponse.json({
      response: responseText,
      ai_score: aiScore,
      ai_comment: aiComment,
      version_id: version_id || null,
    });
  } catch (error) {
    console.error('[Chat Lab] Error evaluating prompt:', error);
    const message = error instanceof Error ? error.message : 'Internal Server Error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
