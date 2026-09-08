import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
export const dynamic = "force-dynamic";

// Per-prompt response tallies from the client events the engine emits
// (Desktop Prompt Shown / Answered / Dismissed), grouped by answer value so
// stars/NPS averages and per-option counts render on the Prompts page.
export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );
  if (!apiKey || !projectId) {
    return NextResponse.json({ available: false, results: [] });
  }

  const days = parseInt(request.nextUrl.searchParams.get("days") || "90", 10);
  try {
    const rows = (await posthogResults(
      host,
      projectId,
      apiKey,
      `
        SELECT
          toString(properties.prompt_id) AS prompt_id,
          event,
          toString(properties.value) AS value,
          count() AS n
        FROM events
        WHERE event IN ('Desktop Prompt Shown', 'Desktop Prompt Answered', 'Desktop Prompt Dismissed')
          AND timestamp >= now() - INTERVAL ${days} DAY
        GROUP BY prompt_id, event, value
        ORDER BY prompt_id
      `,
    )) as any[];
    const byPrompt: Record<
      string,
      {
        shown: number;
        answered: number;
        dismissed: number;
        answers: Record<string, number>;
      }
    > = {};
    for (const [promptId, event, value, n] of rows ?? []) {
      const entry = (byPrompt[promptId] ??= {
        shown: 0,
        answered: 0,
        dismissed: 0,
        answers: {},
      });
      const count = Number(n) || 0;
      if (event === "Desktop Prompt Shown") entry.shown += count;
      else if (event === "Desktop Prompt Dismissed") entry.dismissed += count;
      else {
        entry.answered += count;
        if (value) entry.answers[value] = (entry.answers[value] ?? 0) + count;
      }
    }
    return NextResponse.json({ available: true, results: byPrompt });
  } catch (error) {
    console.error("Prompt results error:", error);
    return NextResponse.json({ available: false, results: {} });
  }
}
