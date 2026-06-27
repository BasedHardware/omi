"use client";

import { useState, useMemo, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Loader2,
  Star,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import useSWR, { mutate as globalMutate } from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";
import {
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  CartesianGrid,
  Legend,
} from "recharts";

// --- Types ---

interface RatingWeek {
  week: string;
  thumbs_up: number;
  thumbs_down: number;
}

interface RatingsData {
  weeks: RatingWeek[];
  total_up: number;
  total_down: number;
}

interface PromptVersion {
  id: string;
  name: string;
  floating_prefix: string;
  prompt_text: string;
  created_at: string;
}

interface PromptsData {
  versions: PromptVersion[];
}

interface Question {
  id: string;
  text: string;
  context_type: string;
  context_data?: string;
}

interface QuestionsData {
  questions: Question[];
}

interface EvaluationResult {
  question_id: string;
  version_id: string;
  response: string;
  ai_score: number;
  human_score: number;
  comment: string;
}

// --- Helpers ---

const CONTEXT_COLORS: Record<string, string> = {
  memories: "bg-blue-500/20 text-blue-400",
  conversations: "bg-green-500/20 text-green-400",
  screen: "bg-purple-500/20 text-purple-400",
  search: "bg-yellow-500/20 text-yellow-400",
  tasks: "bg-orange-500/20 text-orange-400",
};

function contextBadgeClass(type: string): string {
  return CONTEXT_COLORS[type] || "bg-gray-500/20 text-gray-400";
}

// --- Star Rating Component ---

function StarRating({
  value,
  onChange,
  readonly = false,
}: {
  value: number;
  onChange?: (v: number) => void;
  readonly?: boolean;
}) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`h-4 w-4 ${
            i <= value
              ? "fill-yellow-400 text-yellow-400"
              : "text-muted-foreground"
          } ${!readonly ? "cursor-pointer hover:text-yellow-400" : ""}`}
          onClick={() => {
            if (!readonly && onChange) {
              onChange(i === value ? 0 : i);
            }
          }}
        />
      ))}
    </div>
  );
}

// --- Truncatable Text ---

function TruncatableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > 200;

  return (
    <div>
      <p className={`text-sm ${!expanded && isLong ? "line-clamp-3" : ""}`}>
        {text}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-primary hover:underline mt-1 flex items-center gap-1"
        >
          {expanded ? (
            <>
              Show less <ChevronUp className="h-3 w-3" />
            </>
          ) : (
            <>
              Show more <ChevronDown className="h-3 w-3" />
            </>
          )}
        </button>
      )}
    </div>
  );
}

// --- Main Page ---

export default function ChatLabPage() {
  const { token } = useAuthToken();

  // --- Ratings ---
  const { data: ratingsData, isLoading: ratingsLoading } = useSWR<RatingsData>(
    token ? ["/api/omi/chat-lab/ratings", token] : null,
    authenticatedFetcher
  );

  const ratingsStats = useMemo(() => {
    if (!ratingsData) return { total: 0, up: 0, down: 0, pct: 0 };
    const up = ratingsData.total_up;
    const down = ratingsData.total_down;
    const total = up + down;
    return { total, up, down, pct: total > 0 ? Math.round((up / total) * 100) : 0 };
  }, [ratingsData]);

  // --- Prompts ---
  const { data: promptsData, isLoading: promptsLoading } = useSWR<PromptsData>(
    token ? ["/api/omi/chat-lab/prompts", token] : null,
    authenticatedFetcher
  );

  const [selectedVersionId, setSelectedVersionId] = useState<string>("");
  const [editFloatingPrefix, setEditFloatingPrefix] = useState("");
  const [editPromptText, setEditPromptText] = useState("");
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [newVersionName, setNewVersionName] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  // When prompts load or selection changes, populate editor
  const selectedVersion = useMemo(() => {
    if (!promptsData?.versions?.length) return null;
    const id = selectedVersionId || promptsData.versions[0].id;
    return promptsData.versions.find((v) => v.id === id) || promptsData.versions[0];
  }, [promptsData, selectedVersionId]);

  // Sync editor when version changes
  const handleVersionSelect = useCallback(
    (id: string) => {
      setSelectedVersionId(id);
      const v = promptsData?.versions?.find((ver) => ver.id === id);
      if (v) {
        setEditFloatingPrefix(v.floating_prefix);
        setEditPromptText(v.prompt_text);
      }
    },
    [promptsData]
  );

  // Initialize editor on first load
  useMemo(() => {
    if (selectedVersion && !editPromptText && !editFloatingPrefix) {
      setEditFloatingPrefix(selectedVersion.floating_prefix);
      setEditPromptText(selectedVersion.prompt_text);
    }
  }, [selectedVersion, editPromptText, editFloatingPrefix]);

  const handleSaveNewVersion = async () => {
    if (!token || !newVersionName.trim()) return;
    setSaving(true);
    try {
      await fetch("/api/omi/chat-lab/prompts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: newVersionName.trim(),
          floating_prefix: editFloatingPrefix,
          prompt_text: editPromptText,
        }),
      });
      setSaveDialogOpen(false);
      setNewVersionName("");
      globalMutate(
        (key: unknown) => Array.isArray(key) && key[0] === "/api/omi/chat-lab/prompts"
      );
    } catch (e) {
      console.error("Failed to save version:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async () => {
    if (!token) return;
    setGenerating(true);
    try {
      const res = await fetch("/api/omi/chat-lab/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          floating_prefix: editFloatingPrefix,
          prompt_text: editPromptText,
          evaluations,
        }),
      });
      const data = await res.json();
      if (data.floating_prefix) setEditFloatingPrefix(data.floating_prefix);
      if (data.prompt_text) setEditPromptText(data.prompt_text);
    } catch (e) {
      console.error("Failed to generate:", e);
    } finally {
      setGenerating(false);
    }
  };

  // --- Questions ---
  const {
    data: questionsData,
    isLoading: questionsLoading,
    mutate: mutateQuestions,
  } = useSWR<QuestionsData>(
    token ? ["/api/omi/chat-lab/questions", token] : null,
    authenticatedFetcher
  );

  const [refreshingQuestions, setRefreshingQuestions] = useState(false);

  const handleRefreshQuestions = async () => {
    if (!token) return;
    setRefreshingQuestions(true);
    try {
      await fetch("/api/omi/chat-lab/questions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ action: "refresh" }),
      });
      mutateQuestions();
    } catch (e) {
      console.error("Failed to refresh questions:", e);
    } finally {
      setRefreshingQuestions(false);
    }
  };

  // --- Evaluations ---
  const [evaluations, setEvaluations] = useState<Record<string, EvaluationResult>>({});
  const [runningAll, setRunningAll] = useState(false);
  const [runningQuestions, setRunningQuestions] = useState<Set<string>>(new Set());

  const evalKey = (questionId: string, versionId: string) =>
    `${questionId}::${versionId}`;

  const updateEvaluation = (
    questionId: string,
    versionId: string,
    updates: Partial<EvaluationResult>
  ) => {
    const key = evalKey(questionId, versionId);
    setEvaluations((prev) => {
      const base: EvaluationResult = {
        question_id: questionId,
        version_id: versionId,
        response: "",
        ai_score: 0,
        human_score: 0,
        comment: "",
      };
      return {
        ...prev,
        [key]: { ...base, ...prev[key], ...updates },
      };
    });
  };

  const runEvaluation = async (question: Question, versionId: string) => {
    if (!token) return;
    const key = evalKey(question.id, versionId);
    setRunningQuestions((prev) => new Set(prev).add(question.id));
    try {
      const res = await fetch("/api/omi/chat-lab/evaluate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question_id: question.id,
          question_text: question.text,
          context_type: question.context_type,
          context_data: question.context_data,
          version_id: versionId,
          floating_prefix: editFloatingPrefix,
          prompt_text: editPromptText,
        }),
      });
      const data = await res.json();
      updateEvaluation(question.id, versionId, {
        response: data.response || "",
        ai_score: data.ai_score || 0,
      });
    } catch (e) {
      console.error("Evaluation failed:", e);
      updateEvaluation(question.id, versionId, {
        response: "[Error running evaluation]",
        ai_score: 0,
      });
    } finally {
      setRunningQuestions((prev) => {
        const next = new Set(prev);
        next.delete(question.id);
        return next;
      });
    }
  };

  const handleRunAll = async () => {
    if (!token || !questionsData?.questions?.length || !currentVersionId) return;
    setRunningAll(true);
    const questions = questionsData.questions;
    for (const q of questions) {
      await runEvaluation(q, currentVersionId);
    }
    setRunningAll(false);
  };

  const currentVersionId = selectedVersion?.id || "";

  // --- Version columns for evaluation table ---
  const versionColumns = useMemo(() => {
    if (!promptsData?.versions?.length) return [];
    // Show all versions that have evaluations, plus the current one
    const versionIds = new Set<string>();
    if (currentVersionId) versionIds.add(currentVersionId);
    Object.values(evaluations).forEach((ev) => versionIds.add(ev.version_id));
    return promptsData.versions.filter((v) => versionIds.has(v.id));
  }, [promptsData, currentVersionId, evaluations]);

  // --- Version Comparison ---
  const versionAverages = useMemo(() => {
    if (!questionsData?.questions?.length) return [];
    return versionColumns.map((v) => {
      const scores = questionsData.questions
        .map((q) => evaluations[evalKey(q.id, v.id)]?.ai_score)
        .filter((s): s is number => s != null && s > 0);
      const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
      return { id: v.id, name: v.name, avg: Math.round(avg * 10) / 10, count: scores.length };
    });
  }, [versionColumns, evaluations, questionsData]);

  // --- Render ---

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Chat Lab</h1>
      </div>

      {/* Section 1: Production Ratings Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Production Ratings
            {ratingsLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {ratingsData?.weeks?.length ? (
            <>
              <div className="flex gap-6 mb-4 text-sm">
                <div className="flex items-center gap-2">
                  <ThumbsUp className="h-4 w-4 text-green-400" />
                  <span>{ratingsStats.up} positive</span>
                </div>
                <div className="flex items-center gap-2">
                  <ThumbsDown className="h-4 w-4 text-red-400" />
                  <span>{ratingsStats.down} negative</span>
                </div>
                <div className="text-muted-foreground">
                  {ratingsStats.pct}% positive of {ratingsStats.total} total
                </div>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={ratingsData.weeks}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis
                    dataKey="week"
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={12}
                  />
                  <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                      color: "hsl(var(--card-foreground))",
                    }}
                  />
                  <Legend />
                  <Bar
                    dataKey="thumbs_up"
                    name="Thumbs Up"
                    fill="#4ade80"
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="thumbs_down"
                    name="Thumbs Down"
                    fill="#f87171"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </>
          ) : ratingsLoading ? (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              Loading ratings...
            </div>
          ) : (
            <div className="flex items-center justify-center h-[250px] text-muted-foreground">
              No ratings data available
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 2: Prompt Editor */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Prompt Editor</span>
            <div className="flex items-center gap-2">
              {promptsLoading && <Loader2 className="h-4 w-4 animate-spin" />}
              {promptsData?.versions?.length ? (
                <Select
                  value={selectedVersion?.id || ""}
                  onValueChange={handleVersionSelect}
                >
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Select version" />
                  </SelectTrigger>
                  <SelectContent>
                    {promptsData.versions.map((v) => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground mb-1 block">
              Floating Bar Prefix
            </label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 min-h-[80px] resize-y font-mono"
              value={editFloatingPrefix}
              onChange={(e) => setEditFloatingPrefix(e.target.value)}
              placeholder="Enter floating bar prefix..."
            />
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground mb-1 block">
              Main Prompt
            </label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 min-h-[300px] resize-y font-mono"
              value={editPromptText}
              onChange={(e) => setEditPromptText(e.target.value)}
              placeholder="Enter main prompt..."
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={() => setSaveDialogOpen(true)} disabled={saving}>
              <Save className="h-4 w-4 mr-2" />
              Save as New Version
            </Button>
            <Button
              variant="secondary"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4 mr-2" />
              )}
              Generate Next Version
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Save Version Dialog */}
      <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save as New Version</DialogTitle>
            <DialogDescription>
              Enter a name for this prompt version.
            </DialogDescription>
          </DialogHeader>
          <Input
            placeholder="e.g. v3-concise-responses"
            value={newVersionName}
            onChange={(e) => setNewVersionName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveNewVersion();
            }}
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setSaveDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveNewVersion}
              disabled={saving || !newVersionName.trim()}
            >
              {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Section 3: Evaluation Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Evaluation Table</span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefreshQuestions}
                disabled={refreshingQuestions}
              >
                {refreshingQuestions ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                Refresh from Firestore
              </Button>
              <Button
                size="sm"
                onClick={handleRunAll}
                disabled={runningAll || !questionsData?.questions?.length}
              >
                {runningAll ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Run All Questions
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {questionsLoading ? (
            <div className="flex items-center justify-center h-[200px] text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              Loading questions...
            </div>
          ) : !questionsData?.questions?.length ? (
            <div className="flex items-center justify-center h-[200px] text-muted-foreground">
              No questions available. Click &quot;Refresh from Firestore&quot; to load.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-3 px-3 font-medium text-muted-foreground min-w-[250px] sticky left-0 bg-card z-10">
                      Question
                    </th>
                    <th className="text-left py-3 px-3 font-medium text-muted-foreground min-w-[100px]">
                      Context
                    </th>
                    {versionColumns.map((v) => (
                      <th
                        key={v.id}
                        className="text-left py-3 px-3 font-medium text-muted-foreground min-w-[300px]"
                        colSpan={1}
                      >
                        <div className="flex flex-col gap-1">
                          <span>{v.name}</span>
                          <span className="text-xs font-normal">
                            Response / AI Score / Human Score / Comment
                          </span>
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {questionsData.questions.map((q) => (
                    <tr key={q.id} className="border-b hover:bg-muted/50">
                      <td className="py-3 px-3 align-top sticky left-0 bg-card z-10">
                        <div className="flex items-start gap-2">
                          {runningQuestions.has(q.id) && (
                            <Loader2 className="h-4 w-4 animate-spin flex-shrink-0 mt-0.5" />
                          )}
                          <span>{q.text}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 align-top">
                        <Badge
                          variant="secondary"
                          className={contextBadgeClass(q.context_type)}
                        >
                          {q.context_type}
                        </Badge>
                      </td>
                      {versionColumns.map((v) => {
                        const ev = evaluations[evalKey(q.id, v.id)];
                        return (
                          <td key={v.id} className="py-3 px-3 align-top">
                            {ev ? (
                              <div className="space-y-2">
                                <TruncatableText
                                  text={ev.response || "No response"}
                                />
                                <div className="flex items-center gap-3">
                                  <div className="flex items-center gap-1">
                                    <span className="text-xs text-muted-foreground">
                                      AI:
                                    </span>
                                    <StarRating
                                      value={ev.ai_score}
                                      readonly
                                    />
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-xs text-muted-foreground">
                                      Human:
                                    </span>
                                    <StarRating
                                      value={ev.human_score}
                                      onChange={(score) =>
                                        updateEvaluation(q.id, v.id, {
                                          human_score: score,
                                        })
                                      }
                                    />
                                  </div>
                                </div>
                                <input
                                  type="text"
                                  className="w-full rounded border border-input bg-background px-2 py-1 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                                  placeholder="Add comment..."
                                  value={ev.comment}
                                  onChange={(e) =>
                                    updateEvaluation(q.id, v.id, {
                                      comment: e.target.value,
                                    })
                                  }
                                />
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-xs">
                                Not evaluated
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Section 4: Version Comparison Summary */}
      {versionAverages.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Version Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              {versionAverages.map((v, i) => {
                const prev = i > 0 ? versionAverages[i - 1] : null;
                const diff =
                  prev && prev.avg > 0
                    ? Math.round(((v.avg - prev.avg) / prev.avg) * 100)
                    : null;
                return (
                  <div
                    key={v.id}
                    className="flex items-center gap-2 text-sm"
                  >
                    {prev && (
                      <span className="text-muted-foreground">&rarr;</span>
                    )}
                    <span className="font-medium">{v.name}</span>
                    <span className="text-muted-foreground">
                      avg {v.avg.toFixed(1)}
                    </span>
                    {diff !== null && (
                      <span
                        className={
                          diff > 0
                            ? "text-green-400"
                            : diff < 0
                            ? "text-red-400"
                            : "text-muted-foreground"
                        }
                      >
                        ({diff > 0 ? "+" : ""}
                        {diff}%)
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {versionAverages.some((v) => v.count === 0) && (
              <p className="text-xs text-muted-foreground mt-2">
                Some versions have no scored evaluations yet.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
