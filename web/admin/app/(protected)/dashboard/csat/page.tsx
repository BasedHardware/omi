"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuthFetch } from "@/hooks/useAuthToken";

// Copy + trigger editor and stats for the built-in Desktop rating bar
// (Firestore `csat_config/product` + `csat_ratings`) — NOT the Prompts
// survey builder; ad-hoc surveys live under /dashboard/prompts.

type CsatConfig = {
  enabled: boolean;
  title: string;
  body: string;
  thank_you_text: string;
  refer_cta_text: string;
  question_threshold: number;
  comment_max_score: number;
  revision: number;
  updated_at?: number;
  updated_by?: string;
};

type CsatComment = {
  uid: string;
  platform: string;
  score: number;
  comment: string;
  app_version: string;
  created_at: number;
  revision: number;
};

type CsatStats = {
  available: boolean;
  total: number;
  histogram: Record<string, number>;
  avg: number | null;
  comments: CsatComment[];
};

const EMPTY_STATS: CsatStats = {
  available: false,
  total: 0,
  histogram: {},
  avg: null,
  comments: [],
};

function formatTime(unixSeconds: number): string {
  if (!unixSeconds) return "—";
  return new Date(unixSeconds * 1000).toLocaleString();
}

export default function CsatPage() {
  const { fetchWithAuth, token } = useAuthFetch();
  const [config, setConfig] = useState<CsatConfig | null>(null);
  const [stats, setStats] = useState<CsatStats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [partial, setPartial] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      // Both fetches are independent — one failing must not hide the other.
      const [configRes, statsRes] = await Promise.allSettled([
        fetchWithAuth("/api/omi/csat"),
        fetchWithAuth("/api/omi/csat/stats?limit=500"),
      ]);
      let failed = 0;
      if (configRes.status === "fulfilled" && configRes.value.ok) {
        setConfig((await configRes.value.json()).config ?? null);
      } else {
        failed += 1;
      }
      if (statsRes.status === "fulfilled" && statsRes.value.ok) {
        setStats((await statsRes.value.json()) ?? EMPTY_STATS);
      } else {
        failed += 1;
      }
      setPartial(failed === 1);
      setError(failed === 2 ? "load failed" : null);
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      const response = await fetchWithAuth("/api/omi/csat", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: config.enabled,
          title: config.title,
          body: config.body,
          thank_you_text: config.thank_you_text,
          refer_cta_text: config.refer_cta_text,
          question_threshold: config.question_threshold,
          comment_max_score: config.comment_max_score,
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error ?? `save failed (${response.status})`);
      setConfig(body.config ?? config);
      setSavedRevision(body.config?.revision ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  const maxBar = Math.max(1, ...Object.values(stats.histogram));

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">CSAT</h1>
        <p className="text-sm text-muted-foreground">
          Built-in Desktop rating bar — not the Prompts survey builder. Copy
          edits reach clients within ~5 minutes.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          {partial && (
            <p className="text-sm text-amber-600">
              Partially loaded — one source failed; refresh to retry.
            </p>
          )}
          {error && <p className="text-sm text-red-500">{error}</p>}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Copy &amp; trigger</CardTitle>
              <CardDescription>
                One product-wide config; every save bumps the revision clients
                report back with their rating.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {config && (
                <>
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={config.enabled}
                      onCheckedChange={(enabled) =>
                        setConfig({ ...config, enabled })
                      }
                    />
                    <span className="text-sm">
                      Prompt enabled
                      {savedRevision !== null && (
                        <Badge variant="secondary" className="ml-2">
                          revision {savedRevision}
                        </Badge>
                      )}
                    </span>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="csat-title">Title</Label>
                    <Input
                      id="csat-title"
                      value={config.title}
                      onChange={(e) =>
                        setConfig({ ...config, title: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="csat-body">Subtitle (optional)</Label>
                    <Input
                      id="csat-body"
                      value={config.body}
                      onChange={(e) =>
                        setConfig({ ...config, body: e.target.value })
                      }
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label htmlFor="csat-thanks">Thank-you text</Label>
                      <Input
                        id="csat-thanks"
                        value={config.thank_you_text}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            thank_you_text: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="csat-refer">Refer CTA text</Label>
                      <Input
                        id="csat-refer"
                        value={config.refer_cta_text}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            refer_cta_text: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>
                  <div className="flex items-end gap-3">
                    <div className="space-y-1">
                      <Label htmlFor="csat-threshold">
                        Ask after Nth question (1–50)
                      </Label>
                      <Input
                        id="csat-threshold"
                        type="number"
                        className="w-28"
                        min={1}
                        max={50}
                        value={config.question_threshold}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            question_threshold: parseInt(e.target.value) || 3,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="csat-comment-max">
                        Ask comment at score ≤ (1–5)
                      </Label>
                      <Input
                        id="csat-comment-max"
                        type="number"
                        className="w-28"
                        min={1}
                        max={5}
                        value={config.comment_max_score}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            comment_max_score: parseInt(e.target.value) || 3,
                          })
                        }
                      />
                    </div>
                    <Button
                      onClick={save}
                      disabled={saving || !config.title.trim()}
                    >
                      Save
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Saved config: revision {config.revision}
                    {config.updated_at
                      ? ` · last saved ${formatTime(config.updated_at)}`
                      : ""}
                    . Clients refresh within ~5 minutes (5-minute poll + 60s
                    server cache).
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stats</CardTitle>
              <CardDescription>
                One rating per user per platform, from Firestore. The PostHog
                daily chart stays on the Desktop ratings dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!stats.available ? (
                <p className="text-sm text-amber-600">
                  Stats unavailable (N/A) — Firestore read failed. No zeros are
                  shown for a failed read.
                </p>
              ) : (
                <>
                  <div className="flex items-center gap-6 text-sm">
                    <span>
                      <strong>{stats.total}</strong> ratings
                    </span>
                    <span>
                      avg{" "}
                      <strong>
                        {stats.avg === null ? "—" : stats.avg.toFixed(2)}
                      </strong>
                    </span>
                  </div>
                  <div className="space-y-1">
                    {[5, 4, 3, 2, 1].map((score) => {
                      const count = stats.histogram[String(score)] ?? 0;
                      return (
                        <div
                          key={score}
                          className="flex items-center gap-3 text-sm"
                        >
                          <span className="w-6 text-right">{score}★</span>
                          <div className="h-3 flex-1 overflow-hidden rounded bg-muted">
                            <div
                              className="h-full bg-primary"
                              style={{
                                width: `${(count / maxBar) * 100}%`,
                              }}
                            />
                          </div>
                          <span className="w-8 text-right tabular-nums">
                            {count}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">
                      Latest comments ({stats.comments.length} of last{" "}
                      {stats.total})
                    </p>
                    {stats.comments.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No comments yet.
                      </p>
                    ) : (
                      stats.comments.map((c) => (
                        <div
                          key={`${c.platform}_${c.uid}`}
                          className="rounded-md border p-2 text-sm"
                        >
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{c.score}★</span>
                            <span>{c.platform}</span>
                            <span>v{c.app_version || "?"}</span>
                            <span>{formatTime(c.created_at)}</span>
                            <span className="truncate">uid {c.uid}</span>
                          </div>
                          <p className="mt-1 break-words">{c.comment}</p>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
