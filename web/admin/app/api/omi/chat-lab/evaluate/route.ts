import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { ADMIN_LLM_LANES, invokeAdminLlmGateway } from "@/lib/llm-gateway";

export const dynamic = "force-dynamic";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

async function callChatLab(
  system: string,
  messages: ChatMessage[],
): Promise<string> {
  return invokeAdminLlmGateway({
    lane: ADMIN_LLM_LANES.chatLab,
    feature: "admin_chat_lab",
    messages: [{ role: "system", content: system }, ...messages],
  });
}

function buildSystemPrompt(promptText: string, floatingPrefix: string): string {
  const now = new Date().toISOString();
  const combined = floatingPrefix
    ? `${floatingPrefix}\n\n${promptText}`
    : promptText;

  return combined
    .replace(/\{user_name\}/g, "Test User")
    .replace(/\{tz\}/g, "UTC")
    .replace(/\{current_datetime_str\}/g, now);
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { question, prompt_text, floating_prefix, version_id } = body;

    if (!question || !prompt_text) {
      return NextResponse.json(
        { error: "question and prompt_text are required" },
        { status: 400 },
      );
    }

    const systemPrompt = buildSystemPrompt(prompt_text, floating_prefix || "");

    // First call: generate the response
    const responseText = await callChatLab(systemPrompt, [
      { role: "user", content: question },
    ]);

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

    const gradingResult = await callChatLab(gradingSystem, [
      { role: "user", content: gradingPrompt },
    ]);

    let aiScore = 0;
    let aiComment = "";
    try {
      const parsed = JSON.parse(gradingResult);
      aiScore = parsed.score ?? 0;
      aiComment = parsed.comment ?? "";
    } catch {
      // If grading response isn't valid JSON, extract what we can
      aiComment = gradingResult;
      const scoreMatch = gradingResult.match(
        /(\d+(?:\.\d+)?)\s*(?:\/\s*5|out of 5)/,
      );
      if (scoreMatch) aiScore = parseFloat(scoreMatch[1]);
    }

    return NextResponse.json({
      response: responseText,
      ai_score: aiScore,
      ai_comment: aiComment,
      version_id: version_id || null,
    });
  } catch (error) {
    console.error("[Chat Lab] Error evaluating prompt:", error);
    const message =
      error instanceof Error ? error.message : "Internal Server Error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
