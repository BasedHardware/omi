"use client";

import useSWR from "swr";
import { Loader2, AlertTriangle, ExternalLink } from "lucide-react";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface ReleaseRow {
  version: string;
  tag: string;
  published_at: string;
  html_url: string;
  crash_rate: number | null;
  crash_count: number | null;
  session_count: number | null;
  feedback_count: number | null;
  broken_count: number | null;
  rating: number | null;
  summary: string | null;
}

interface ReleasesResponse {
  releases: ReleaseRow[];
  github_error: string | null;
  posthog_error: string | null;
  partial: boolean;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function CrashRateCell({ row }: { row: ReleaseRow }) {
  if (row.crash_rate === null || row.session_count === null) {
    return <span className="text-muted-foreground">—</span>;
  }
  const pct = row.crash_rate * 100;
  const color =
    pct >= 2 ? "text-red-500" : pct >= 0.5 ? "text-amber-500" : "text-emerald-500";
  return (
    <div className="flex flex-col">
      <span className={cn("font-mono font-semibold", color)}>
        {pct.toFixed(2)}%
      </span>
      <span className="text-[11px] text-muted-foreground font-mono">
        {row.crash_count?.toLocaleString()} / {row.session_count?.toLocaleString()} sessions
      </span>
    </div>
  );
}

function RatingBadge({ rating }: { rating: number | null }) {
  if (rating === null) return <span className="text-muted-foreground">—</span>;
  const color =
    rating >= 4
      ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/30"
      : rating >= 2.5
        ? "bg-amber-500/15 text-amber-500 border-amber-500/30"
        : "bg-red-500/15 text-red-500 border-red-500/30";
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-md border px-2.5 py-1 font-mono font-bold text-base",
        color
      )}
    >
      {rating.toFixed(1)}
    </span>
  );
}

function FeedbackCell({ row }: { row: ReleaseRow }) {
  const fb = row.feedback_count ?? 0;
  const broken = row.broken_count ?? 0;
  if (fb === 0 && broken === 0) {
    return <span className="text-muted-foreground text-xs">none</span>;
  }
  return (
    <div className="flex flex-col gap-0.5">
      {fb > 0 && (
        <span className="text-xs">
          <span className="font-semibold">{fb}</span>{" "}
          <span className="text-muted-foreground">feedback{fb !== 1 ? "s" : ""}</span>
        </span>
      )}
      {broken > 0 && (
        <span className="text-xs">
          <span className="font-semibold">{broken}</span>{" "}
          <span className="text-muted-foreground">capture failures</span>
        </span>
      )}
    </div>
  );
}

export default function ReleasesPage() {
  const { token } = useAuthToken();
  const { data, error, isLoading } = useSWR<ReleasesResponse>(
    token ? ["/api/omi/releases", token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false, refreshInterval: 5 * 60 * 1000 }
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-2">
        <AlertTriangle className="h-8 w-8 text-red-500" />
        <p className="text-sm text-muted-foreground">
          Failed to load releases: {String(error?.message || error)}
        </p>
      </div>
    );
  }

  const releases = data?.releases ?? [];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Desktop Releases</h1>

      {data?.partial && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-500">
          <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <span>
            {data.posthog_error
              ? `PostHog unavailable: ${data.posthog_error}`
              : "Some metrics may be incomplete."}
          </span>
        </div>
      )}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[100px]">Version</TableHead>
              <TableHead className="w-[140px]">Released</TableHead>
              <TableHead className="w-[140px]">Crash Rate</TableHead>
              <TableHead className="w-[120px]">Issues</TableHead>
              <TableHead className="w-[60px] text-center">Rating</TableHead>
              <TableHead>Summary</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {releases.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="text-center py-8 text-muted-foreground"
                >
                  No releases found.
                </TableCell>
              </TableRow>
            )}
            {releases.map((r) => (
              <TableRow key={r.tag}>
                <TableCell className="font-mono text-sm">
                  <a
                    href={r.html_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 hover:underline"
                  >
                    {r.version}
                    <ExternalLink className="h-3 w-3 opacity-40" />
                  </a>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {formatDate(r.published_at)}
                </TableCell>
                <TableCell>
                  <CrashRateCell row={r} />
                </TableCell>
                <TableCell>
                  <FeedbackCell row={r} />
                </TableCell>
                <TableCell className="text-center">
                  <RatingBadge rating={r.rating} />
                </TableCell>
                <TableCell className="text-sm max-w-sm">
                  {r.summary || <span className="text-muted-foreground">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
