"use client";

import { useCallback, useRef, useState } from "react";
import { Loader2, Send, StopCircle } from "lucide-react";
import { useAuthFetch } from "@/hooks/useAuthToken";

type Model = "claude" | "codex";

type RunState =
  | { kind: "idle" }
  | { kind: "running"; lines: string[]; abort: AbortController }
  | { kind: "finished"; lines: string[]; code: number | null }
  | { kind: "error"; lines: string[]; message: string };

const MODEL_LABEL: Record<Model, string> = {
  claude: "Claude Code",
  codex: "Codex",
};

export function AgentPromptWidget() {
  const { fetchWithAuth } = useAuthFetch();
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState<Model>("claude");
  const [state, setState] = useState<RunState>({ kind: "idle" });
  const logRef = useRef<HTMLDivElement | null>(null);

  const append = useCallback((text: string) => {
    setState((cur) => {
      if (cur.kind !== "running" && cur.kind !== "error") return cur;
      const lines = [...cur.lines, text];
      // autoscroll on next frame
      requestAnimationFrame(() => {
        logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
      });
      return { ...cur, lines };
    });
  }, []);

  const submit = async () => {
    if (!prompt.trim()) return;
    const abort = new AbortController();
    setState({ kind: "running", lines: [], abort });

    try {
      const res = await fetchWithAuth("/api/omi/agent/customize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim(), model }),
        signal: abort.signal,
      });

      if (!res.ok || !res.body) {
        const errText = await res.text().catch(() => "");
        setState({
          kind: "error",
          lines: [],
          message: errText || `HTTP ${res.status}`,
        });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line
        let frameEnd: number;
        while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          const event = parseSseFrame(frame);
          if (!event) continue;

          if (event.type === "stdout" || event.type === "stderr") {
            const txt = (event.data?.text as string) ?? "";
            if (txt) append(txt);
          } else if (event.type === "error") {
            const msg = (event.data?.message as string) ?? "Unknown error";
            setState((cur) => ({
              kind: "error",
              lines: cur.kind === "running" ? cur.lines : [],
              message: msg,
            }));
          } else if (event.type === "done") {
            const code = (event.data?.code as number | null) ?? null;
            setState((cur) => ({
              kind: "finished",
              lines: cur.kind === "running" ? cur.lines : [],
              code,
            }));
          } else if (event.type === "status") {
            const phase = (event.data?.phase as string) ?? "";
            const cwd = (event.data?.cwd as string) ?? "";
            append(`▶ starting ${MODEL_LABEL[model]} (${phase}) in ${cwd}\n`);
          }
        }
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        setState((cur) => ({
          kind: "finished",
          lines: cur.kind === "running" ? cur.lines : [],
          code: null,
        }));
      } else {
        setState({
          kind: "error",
          lines: [],
          message: err?.message ?? "Network error",
        });
      }
    }
  };

  const stop = () => {
    if (state.kind === "running") state.abort.abort();
  };

  const reset = () => {
    setState({ kind: "idle" });
    setPrompt("");
  };

  const lines =
    state.kind === "running" || state.kind === "finished" || state.kind === "error"
      ? state.lines
      : [];
  const showLog = state.kind !== "idle";
  const running = state.kind === "running";

  return (
    <div className="flex h-full flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        Describe a change. The agent runs locally with full repo access, edits files in
        your worktree, and Next HMR reloads the dashboard as it goes.
      </p>

      {!showLog && (
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder='e.g., "Add a chart of weekly desktop signups split by macOS version"'
          className="min-h-0 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      )}

      {showLog && (
        <div
          ref={logRef}
          className="min-h-0 flex-1 overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-snug"
        >
          {lines.length === 0 && running && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> waiting for output…
            </div>
          )}
          {lines.map((l, i) => (
            <pre key={i} className="whitespace-pre-wrap break-words">
              {l}
            </pre>
          ))}
          {state.kind === "error" && (
            <pre className="mt-2 whitespace-pre-wrap break-words text-destructive">
              error: {state.message}
            </pre>
          )}
          {state.kind === "finished" && (
            <pre className={`mt-2 ${state.code === 0 ? "text-green-600" : "text-amber-600"}`}>
              {state.code === 0
                ? "✓ done (exit 0)"
                : state.code == null
                  ? "■ stopped"
                  : `✗ exited ${state.code}`}
            </pre>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-input text-xs font-medium">
          {(["claude", "codex"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModel(m)}
              disabled={running}
              className={`px-2.5 py-1 transition-colors ${
                model === m
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              } disabled:opacity-50`}
            >
              {MODEL_LABEL[m]}
            </button>
          ))}
        </div>

        {showLog ? (
          <>
            {running && (
              <button
                type="button"
                onClick={stop}
                className="inline-flex items-center gap-1 rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium hover:bg-accent"
              >
                <StopCircle className="h-3.5 w-3.5" /> Stop
              </button>
            )}
            {!running && (
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1 rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium hover:bg-accent"
              >
                New prompt
              </button>
            )}
          </>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!prompt.trim()}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" /> Send to {MODEL_LABEL[model]}
          </button>
        )}
      </div>
    </div>
  );
}

function parseSseFrame(frame: string): { type: string; data: any } | null {
  let type = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  }
  if (dataLines.length === 0) return null;
  try {
    return { type, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { type, data: { text: dataLines.join("\n") } };
  }
}
