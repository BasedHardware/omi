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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAuthFetch } from "@/hooks/useAuthToken";

// Remote in-app prompts for Omi Desktop. Create/toggle here; every client
// picks the change up within ~5 minutes — no app release. Responses arrive
// as PostHog events and are tallied per prompt below.

type Prompt = {
  id: string;
  type: string;
  question: string;
  active: boolean;
  options?: string[];
  cta?: { label: string; url: string } | null;
  trigger?: { kind: string; count: number };
  audience?: { rollout_pct?: number; channels?: string[] };
};

type PromptResults = Record<
  string,
  {
    shown: number;
    answered: number;
    dismissed: number;
    answers: Record<string, number>;
  }
>;

const TYPE_LABELS: Record<string, string> = {
  stars: "Stars 1-5",
  nps: "NPS 0-10",
  choice: "Multiple choice",
  banner: "Banner + button",
};

function summarizeAnswers(
  type: string,
  answers: Record<string, number>,
): string {
  const entries = Object.entries(answers);
  if (entries.length === 0) return "—";
  if (type === "stars" || type === "nps") {
    let total = 0;
    let count = 0;
    for (const [value, n] of entries) {
      const v = parseFloat(value);
      if (!Number.isNaN(v)) {
        total += v * n;
        count += n;
      }
    }
    return count > 0 ? `avg ${(total / count).toFixed(2)} (${count})` : "—";
  }
  return entries
    .sort((a, b) => b[1] - a[1])
    .map(([value, n]) => `${value}: ${n}`)
    .join(" · ");
}

export default function PromptsPage() {
  const { fetchWithAuth, token } = useAuthFetch();
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [results, setResults] = useState<PromptResults>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    type: "stars",
    question: "",
    options: "",
    ctaLabel: "",
    ctaUrl: "",
    triggerKind: "question_count",
    triggerCount: 3,
    rolloutPct: 100,
  });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [promptsRes, resultsRes] = await Promise.all([
        fetchWithAuth("/api/omi/desktop-prompts"),
        fetchWithAuth("/api/omi/desktop-prompts/results"),
      ]);
      if (!promptsRes.ok) throw new Error(`load failed (${promptsRes.status})`);
      setPrompts((await promptsRes.json()).prompts ?? []);
      if (resultsRes.ok) setResults((await resultsRes.json()).results ?? {});
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  async function create() {
    setSaving(true);
    try {
      const response = await fetchWithAuth("/api/omi/desktop-prompts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: form.type,
          question: form.question,
          options: form.options
            .split("\n")
            .map((o) => o.trim())
            .filter(Boolean),
          cta_label: form.ctaLabel || undefined,
          cta_url: form.ctaUrl || undefined,
          trigger_kind: form.triggerKind,
          trigger_count: form.triggerCount,
          rollout_pct: form.rolloutPct,
          active: false,
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error ?? `create failed (${response.status})`);
      setForm({ ...form, question: "", options: "", ctaLabel: "", ctaUrl: "" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    } finally {
      setSaving(false);
    }
  }

  async function setActive(prompt: Prompt, active: boolean) {
    setPrompts((current) =>
      current.map((p) => (p.id === prompt.id ? { ...p, active } : p)),
    );
    await fetchWithAuth(`/api/omi/desktop-prompts/${prompt.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    });
  }

  async function remove(prompt: Prompt) {
    if (!window.confirm(`Delete prompt "${prompt.question}"?`)) return;
    await fetchWithAuth(`/api/omi/desktop-prompts/${prompt.id}`, {
      method: "DELETE",
    });
    await load();
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-semibold">Desktop prompts</h1>
        <p className="text-sm text-muted-foreground">
          In-app surveys and banners for Omi Desktop. Toggling here reaches
          every client within ~5 minutes — no release. One prompt shows at a
          time, once per user.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New prompt</CardTitle>
          <CardDescription>
            Created inactive — flip the switch when ready.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-3">
            <Select
              value={form.type}
              onValueChange={(type) => setForm({ ...form, type })}
            >
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Question — e.g. How useful was today's summary?"
              value={form.question}
              onChange={(e) => setForm({ ...form, question: e.target.value })}
            />
          </div>
          {form.type === "choice" && (
            <textarea
              className="w-full rounded-md border bg-transparent p-2 text-sm"
              rows={3}
              placeholder={"One option per line (2-6)"}
              value={form.options}
              onChange={(e) => setForm({ ...form, options: e.target.value })}
            />
          )}
          {form.type === "banner" && (
            <div className="flex gap-3">
              <Input
                placeholder="Button label"
                value={form.ctaLabel}
                onChange={(e) => setForm({ ...form, ctaLabel: e.target.value })}
              />
              <Input
                placeholder="Button URL"
                value={form.ctaUrl}
                onChange={(e) => setForm({ ...form, ctaUrl: e.target.value })}
              />
            </div>
          )}
          <div className="flex items-center gap-3 text-sm">
            <Select
              value={form.triggerKind}
              onValueChange={(triggerKind) => setForm({ ...form, triggerKind })}
            >
              <SelectTrigger className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="question_count">
                  After Nth question
                </SelectItem>
                <SelectItem value="app_launch">On app launch</SelectItem>
              </SelectContent>
            </Select>
            {form.triggerKind === "question_count" && (
              <Input
                type="number"
                className="w-20"
                min={1}
                value={form.triggerCount}
                onChange={(e) =>
                  setForm({
                    ...form,
                    triggerCount: parseInt(e.target.value) || 1,
                  })
                }
              />
            )}
            <span className="text-muted-foreground">Rollout %</span>
            <Input
              type="number"
              className="w-20"
              min={1}
              max={100}
              value={form.rolloutPct}
              onChange={(e) =>
                setForm({
                  ...form,
                  rolloutPct: parseInt(e.target.value) || 100,
                })
              }
            />
            <Button onClick={create} disabled={saving || !form.question.trim()}>
              Create
            </Button>
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        prompts.map((prompt) => {
          const tally = results[prompt.id];
          return (
            <Card key={prompt.id}>
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">
                      {prompt.question}
                    </span>
                    <Badge variant="outline">
                      {TYPE_LABELS[prompt.type] ?? prompt.type}
                    </Badge>
                    {prompt.trigger?.kind === "question_count" && (
                      <Badge variant="secondary">
                        after Q{prompt.trigger.count}
                      </Badge>
                    )}
                    {(prompt.audience?.rollout_pct ?? 100) < 100 && (
                      <Badge variant="secondary">
                        {prompt.audience?.rollout_pct}%
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {tally
                      ? `${tally.shown} shown · ${tally.answered} answered · ${tally.dismissed} dismissed · ${summarizeAnswers(prompt.type, tally.answers)}`
                      : "no responses yet"}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <Switch
                    checked={prompt.active}
                    onCheckedChange={(active) => void setActive(prompt, active)}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void remove(prompt)}
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}
