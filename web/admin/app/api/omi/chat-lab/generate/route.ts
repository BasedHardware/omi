import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

interface Evaluation {
  question: string;
  response: string;
  ai_score: number;
  human_score?: number;
  human_comment?: string;
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { current_prompt, evaluations } = body as {
      current_prompt: string;
      evaluations: Evaluation[];
    };

    if (!current_prompt || !Array.isArray(evaluations) || evaluations.length === 0) {
      return NextResponse.json(
        { error: 'current_prompt and non-empty evaluations array are required' },
        { status: 400 }
      );
    }

    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: 'ANTHROPIC_API_KEY is not configured' }, { status: 500 });
    }

    const evalsFormatted = evaluations
      .map(
        (e, i) =>
          `--- Evaluation ${i + 1} ---
Question: ${e.question}
Response: ${e.response}
AI Score: ${e.ai_score}/5
${e.human_score != null ? `Human Score: ${e.human_score}/5` : 'Human Score: not provided'}
${e.human_comment ? `Human Comment: ${e.human_comment}` : ''}`
      )
      .join('\n\n');

    const metaPrompt = `You are a prompt engineer specializing in conversational AI assistants. Your task is to improve a system prompt based on evaluation results.

Here is the current system prompt:
<current_prompt>
${current_prompt}
</current_prompt>

Here are the evaluation results from testing this prompt with real user questions:
<evaluations>
${evalsFormatted}
</evaluations>

Analyze the evaluation results and generate an improved version of the system prompt. Focus on:
1. Questions that scored poorly — what went wrong and how the prompt can be adjusted
2. Patterns in human feedback — what do humans want that the AI isn't delivering
3. Maintaining what already works well (high-scoring responses)
4. Keeping the prompt concise and clear

Respond ONLY with valid JSON in this exact format:
{
  "prompt_text": "<the improved main system prompt>",
  "floating_prefix": "<a short prefix that appears before the main prompt, used for personality/tone guidance>",
  "notes": "<brief explanation of what you changed and why>"
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        messages: [{ role: 'user', content: metaPrompt }],
      }),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Claude API error ${response.status}: ${errorBody}`);
    }

    const data = await response.json();
    const textBlock = data.content?.find((block: { type: string }) => block.type === 'text');
    const resultText = textBlock?.text || '';

    try {
      // Try to extract JSON from the response (handle markdown code blocks)
      const jsonMatch = resultText.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('No JSON found in response');
      }
      const parsed = JSON.parse(jsonMatch[0]);
      return NextResponse.json({
        prompt_text: parsed.prompt_text || '',
        floating_prefix: parsed.floating_prefix || '',
        notes: parsed.notes || '',
      });
    } catch {
      // Return raw text if JSON parsing fails
      return NextResponse.json({
        prompt_text: resultText,
        floating_prefix: '',
        notes: 'Warning: Could not parse structured response from Claude. Raw text returned as prompt_text.',
      });
    }
  } catch (error) {
    console.error('[Chat Lab] Error generating prompt:', error);
    const message = error instanceof Error ? error.message : 'Internal Server Error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
