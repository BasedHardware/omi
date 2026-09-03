"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuthFetch } from "@/hooks/useAuthToken";

// Daily thumbs-down report. The list of entries is pointers only — the report
// document holds message ids, senders and timestamps, never text. Expanding an
// entry calls the context route, which asks the backend to decrypt that one
// conversation window for this request. That is why context loads per-row
// instead of arriving with the report.

type FeedbackEvent = {
  id: string;
  uid: string;
  surface: string;
  target_kind: string;
  target_id: string;
  value: number;
  created_at: string;
  reason?: string | null;
  comment?: string | null;
  platform?: string | null;
  app_version?: string | null;
  chat_session_id?: string | null;
  prompt_name?: string | null;
  prompt_commit?: string | null;
};

type ContextTurn = {
  message_id: string;
  sender: string;
  created_at: string;
  position: "before" | "rated" | "after";
  seconds_from_rated: number;
};

type ContextPointer = {
  event_id: string;
  target_kind: string;
  turns: ContextTurn[];
  follow_up_count: number;
  follow_up_window_seconds: number;
  truncated_before: boolean;
  truncated_after: boolean;
  resolution_error?: string | null;
};

type ReportEntry = { event: FeedbackEvent; context: ContextPointer };

type Report = {
  date: string;
  generated_at: string;
  total_negative: number;
  counts_by_surface: Record<string, number>;
  counts_by_reason: Record<string, number>;
  counts_by_platform: Record<string, number>;
  entries: ReportEntry[];
  truncated: boolean;
};

type HydratedTurn = ContextTurn & { text: string };
type HydratedContext = {
  event_id: string;
  turns: HydratedTurn[];
  unavailable: string[];
};

const SURFACE_LABELS: Record<string, string> = {
  chat_text: "Chat",
  chat_voice: "Voice",
  chat_notification: "Notification card",
  conversation_summary: "Summary",
  memory: "Memory",
};

const REASON_LABELS: Record<string, string> = {
  too_verbose: "Too long",
  incorrect_or_hallucination: "Incorrect",
  not_helpful_or_irrelevant: "Not helpful",
  didnt_follow_instructions: "Ignored instructions",
  other: "Other",
  not_captured: "Not captured",
};

function yesterdayUtc(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function formatOffset(seconds: number): string {
  if (seconds === 0) return "rated";
  const sign = seconds < 0 ? "−" : "+";
  const abs = Math.abs(seconds);
  if (abs < 60) return `${sign}${abs}s`;
  return `${sign}${Math.floor(abs / 60)}m${abs % 60 ? ` ${abs % 60}s` : ""}`;
}

function CountRow({
  title,
  counts,
  labels,
}: {
  title: string;
  counts: Record<string, number>;
  labels?: Record<string, string>;
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      {entries.length === 0 ? (
        <div className="text-sm text-muted-foreground">—</div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {entries.map(([key, count]) => (
            <Badge key={key} variant="secondary">
              {labels?.[key] ?? key}: {count}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * What the window actually says about this thumbs-down.
 *
 * "The user stopped here" is a claim about the user's behaviour, and it is only
 * true when we successfully looked for follow-up turns and found none. It is
 * wrong for a summary or memory rating (there is no turn stream to follow up
 * in) and wrong when the window could not be resolved at all — in both cases
 * the honest answer is that we do not know, not that the user gave up.
 */
function followUpSummary(entry: ReportEntry): string {
  const { context } = entry;
  if (context.target_kind !== "chat_message") {
    return "No conversation window — this rating is on a single artifact.";
  }
  if (context.resolution_error) {
    return "Follow-up unknown — the conversation window could not be resolved.";
  }
  if (context.follow_up_count > 0) {
    const minutes = Math.round(context.follow_up_window_seconds / 60);
    return `${context.follow_up_count} follow-up turn(s) within ${minutes} min`;
  }
  const minutes = Math.round(context.follow_up_window_seconds / 60);
  return `No follow-up within ${minutes} min — the user stopped here.`;
}

function EntryCard({
  entry,
  reportDate,
  fetchWithAuth,
}: {
  entry: ReportEntry;
  reportDate: string;
  fetchWithAuth: (url: string, init?: RequestInit) => Promise<Response>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [context, setContext] = useState<HydratedContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { event } = entry;

  const toggle = useCallback(async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (context || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth(
        `/api/omi/feedback/events/${encodeURIComponent(
          event.id
        )}/context?report_date=${encodeURIComponent(reportDate)}`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          body?.error || `Failed to load context (${res.status})`
        );
      }
      setContext(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load context");
    } finally {
      setLoading(false);
    }
  }, [expanded, context, loading, event.id, reportDate, fetchWithAuth]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{SURFACE_LABELS[event.surface] ?? event.surface}</Badge>
          <Badge variant="outline">
            {REASON_LABELS[event.reason ?? "not_captured"] ?? event.reason}
          </Badge>
          {event.platform && (
            <Badge variant="secondary">
              {event.platform}
              {event.app_version ? ` ${event.app_version}` : ""}
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">
            {new Date(event.created_at).toLocaleString()}
          </span>
          <span className="ml-auto text-xs text-muted-foreground">
            uid {event.uid.slice(0, 8)}…
          </span>
        </div>
        {event.comment && (
          <CardDescription className="pt-2 italic">
            “{event.comment}”
          </CardDescription>
        )}
        <div className="pt-1 text-xs text-muted-foreground">
          {followUpSummary(entry)}
          {entry.context.truncated_before && " · earlier turns truncated"}
          {entry.context.truncated_after && " · later turns truncated"}
          {entry.context.resolution_error &&
            ` · context unavailable (${entry.context.resolution_error})`}
          {event.prompt_name &&
            ` · prompt ${event.prompt_name}${
              event.prompt_commit ? `@${event.prompt_commit.slice(0, 7)}` : ""
            }`}
        </div>
      </CardHeader>
      <CardContent>
        <Button variant="outline" size="sm" onClick={toggle}>
          {expanded ? "Hide conversation" : "Show conversation"}
        </Button>

        {expanded && loading && (
          <div className="pt-3 text-sm text-muted-foreground">
            Decrypting conversation…
          </div>
        )}
        {expanded && error && (
          <div className="pt-3 text-sm text-destructive">{error}</div>
        )}
        {expanded && context && (
          <div className="space-y-2 pt-3">
            {context.turns.length === 0 && (
              <div className="text-sm text-muted-foreground">
                No turns could be read back for this event.
              </div>
            )}
            {context.turns.map((turn) => (
              <div
                key={turn.message_id}
                className={
                  turn.position === "rated"
                    ? "rounded border-l-4 border-destructive bg-muted/50 p-2"
                    : "rounded border-l-4 border-transparent p-2"
                }
              >
                <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium">
                    {turn.sender === "human" ? "User" : "Omi"}
                  </span>
                  <span>{formatOffset(turn.seconds_from_rated)}</span>
                  {turn.position === "rated" && (
                    <Badge
                      variant="destructive"
                      className="h-4 px-1 text-[10px]"
                    >
                      thumbs down
                    </Badge>
                  )}
                  {turn.position === "after" && (
                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                      follow-up
                    </Badge>
                  )}
                </div>
                <div className="whitespace-pre-wrap text-sm">{turn.text}</div>
              </div>
            ))}
            {context.unavailable.length > 0 && (
              <div className="text-xs text-muted-foreground">
                {context.unavailable.length} turn(s) deleted since the report
                ran.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function FeedbackPage() {
  const { fetchWithAuth, token } = useAuthFetch();
  const [date, setDate] = useState(yesterdayUtc());
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Which date the newest in-flight load is for. A day with hundreds of
  // entries can still be in flight when the user picks another date; without
  // this the slower response wins the race and paints the previous day's
  // report under the newly selected date, with nothing on screen saying so.
  const latestRequest = useRef(0);

  const load = useCallback(
    async (target: string) => {
      const requestId = ++latestRequest.current;
      const isCurrent = () => latestRequest.current === requestId;

      setLoading(true);
      setError(null);
      try {
        const res = await fetchWithAuth(
          `/api/omi/feedback/reports/${encodeURIComponent(target)}`
        );
        if (!isCurrent()) return;
        if (res.status === 404) {
          setReport(null);
          setError(
            `No report for ${target} yet. The nightly job may not have run — generate it below.`
          );
          return;
        }
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            body?.error || `Failed to load report (${res.status})`
          );
        }
        const body = await res.json();
        if (!isCurrent()) return;
        setReport(body);
      } catch (e) {
        if (!isCurrent()) return;
        setReport(null);
        setError(e instanceof Error ? e.message : "Failed to load report");
      } finally {
        if (isCurrent()) setLoading(false);
      }
    },
    [fetchWithAuth]
  );

  useEffect(() => {
    if (token) void load(date);
  }, [token, date, load]);

  const generate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetchWithAuth(
        `/api/omi/feedback/reports/${encodeURIComponent(date)}`,
        { method: "POST" }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error || `Failed to generate (${res.status})`);
      }
      await load(date);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate report");
    } finally {
      setGenerating(false);
    }
  }, [date, fetchWithAuth, load]);

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Negative feedback</h1>
        <p className="text-sm text-muted-foreground">
          Every thumbs-down of a UTC day, with the conversation around it. The
          report stores pointers only; conversation text is decrypted per
          request when you expand an entry, and each read is logged.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-9 rounded-md border bg-background px-3 text-sm"
        />
        <Button
          variant="outline"
          onClick={() => void load(date)}
          disabled={loading}
        >
          {loading ? "Loading…" : "Reload"}
        </Button>
        <Button onClick={() => void generate()} disabled={generating}>
          {generating ? "Generating…" : "Regenerate"}
        </Button>
      </div>

      {error && <div className="text-sm text-destructive">{error}</div>}

      {report && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>
                {report.total_negative} thumbs-down on {report.date}
              </CardTitle>
              <CardDescription>
                Generated {new Date(report.generated_at).toLocaleString()}
                {report.truncated && " · report capped, more events exist"}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <CountRow
                title="Surface"
                counts={report.counts_by_surface}
                labels={SURFACE_LABELS}
              />
              <CountRow
                title="Reason"
                counts={report.counts_by_reason}
                labels={REASON_LABELS}
              />
              <CountRow title="Platform" counts={report.counts_by_platform} />
            </CardContent>
          </Card>

          <div className="space-y-3">
            {report.entries.map((entry) => (
              <EntryCard
                key={entry.event.id}
                entry={entry}
                reportDate={report.date}
                fetchWithAuth={fetchWithAuth}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
