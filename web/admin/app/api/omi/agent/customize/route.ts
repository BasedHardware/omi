import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { localAgentEnabled, localAgentSpawnEnv } from "@/lib/local-agent";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_PROMPT_LEN = 8000;

// Repo-aware preamble. Prepended to every user prompt so the agent has
// the same orientation a fresh contributor would get from CLAUDE.md.
const CONTEXT_PREAMBLE = `You are editing the OMI admin dashboard.

Repo orientation:
- Admin Next.js app: web/admin/
- Main "Dashboard" (formerly Analytics) page: web/admin/app/(protected)/dashboard/page.tsx
- Every widget on that page is a ChartItem in a single ResizableChartGrid.
  Add new widgets to the unifiedItems array; they become draggable, resizable,
  and deletable for free.
- Grid component: web/admin/components/dashboard/resizable-chart-grid.tsx
  (variant: "card" | "header" | "kpi"; col snap: 2/3/4/6/8/9/12; rows 1-12)
- All API access uses useAuthToken + authenticatedFetcher (SWR reads) or
  useAuthFetch (mutations). Server routes call requireScope from @/lib/auth.
- Existing stats endpoints live under web/admin/app/api/omi/stats/.
- Constraints: stay inside web/admin/. Do not touch backend/, app/, firmware/.
- When done, run \`npx tsc --noEmit\` from web/admin/ to verify.

User request:
`;

type Model = "claude" | "codex";

// CLI invocations. Each binary's flags are exactly what the user runs by hand.
// The full prompt (preamble + user text) is appended as the final positional arg.
const COMMANDS: Record<Model, { bin: string; args: string[] }> = {
  claude: {
    bin: "claude",
    // --print for non-interactive one-shot output. The user-requested
    // --dangerously-skip-permissions and --chrome flags pass through.
    args: ["--dangerously-skip-permissions", "--chrome", "--print"],
  },
  codex: {
    bin: "codex",
    // exec is codex's non-interactive subcommand.
    args: ["exec", "--dangerously-bypass-approvals-and-sandbox"],
  },
};

function defaultWorkingDir(): string {
  // The Next dev server runs from web/admin/. Edits should target the worktree
  // root (two dirs up) so the agent can touch the whole admin app and any
  // shared bits at the repo root if it has to.
  return (
    process.env.AGENT_WORKING_DIR ?? path.resolve(process.cwd(), "..", "..")
  );
}

/** Reports whether the local agent endpoint is usable; the widget hides while false. */
export async function GET(request: NextRequest) {
  const auth = await requireScope(request, "dev:agent");
  if (auth instanceof NextResponse) return auth;
  return auth.json({ enabled: localAgentEnabled() });
}

export async function POST(request: NextRequest) {
  const auth = await requireScope(request, "dev:agent");
  if (auth instanceof NextResponse) return auth;

  // The spawn is a local-development tool only: outside it (or without the
  // explicit opt-in) the endpoint does not exist, whatever the caller's role.
  if (!localAgentEnabled()) {
    return new NextResponse(null, { status: 404 });
  }

  let body: { prompt?: string; model?: string };
  try {
    body = await request.json();
  } catch {
    return auth.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const prompt = (body.prompt ?? "").trim();
  if (!prompt) {
    return auth.json({ error: "prompt is required" }, { status: 400 });
  }
  if (prompt.length > MAX_PROMPT_LEN) {
    return auth.json(
      { error: `prompt exceeds ${MAX_PROMPT_LEN} chars` },
      { status: 400 }
    );
  }

  const modelInput = (body.model ?? "claude") as Model;
  const cmd = COMMANDS[modelInput];
  if (!cmd) {
    return auth.json(
      { error: `unknown model "${modelInput}". Use "claude" or "codex".` },
      { status: 400 }
    );
  }

  const cwd = defaultWorkingDir();
  const fullPrompt = CONTEXT_PREAMBLE + prompt;

  // SSE stream. Each event is one JSON-encoded payload.
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      const send = (event: string, data: unknown) => {
        try {
          controller.enqueue(
            enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
          );
        } catch {
          // controller may already be closed if the client disconnected
        }
      };

      send("status", {
        phase: "starting",
        model: modelInput,
        bin: cmd.bin,
        args: cmd.args,
        cwd,
      });

      let child: ChildProcess;
      try {
        child = spawn(cmd.bin, [...cmd.args, fullPrompt], {
          cwd,
          env: localAgentSpawnEnv(),
          stdio: ["ignore", "pipe", "pipe"],
        });
      } catch (err: any) {
        send("error", {
          message: `Failed to spawn ${cmd.bin}: ${
            err?.message ?? "unknown error"
          }. Is it on PATH?`,
        });
        controller.close();
        return;
      }

      child.stdout?.on("data", (chunk: Buffer) => {
        send("stdout", { text: chunk.toString("utf8") });
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        send("stderr", { text: chunk.toString("utf8") });
      });
      child.on("error", (err: Error) => {
        send("error", {
          message: `${cmd.bin} failed to start: ${err.message}. Make sure it's installed and on PATH.`,
        });
        controller.close();
      });
      child.on("close", (code) => {
        send("done", { code });
        controller.close();
      });

      // If the client disconnects, kill the subprocess so we don't leak
      // a runaway agent on the dev box.
      request.signal.addEventListener("abort", () => {
        child.kill("SIGTERM");
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      // Disable nginx-style buffering on any reverse proxy in front.
      "X-Accel-Buffering": "no",
    },
  });
}
