"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ChevronDown, ChevronRight, ShieldCheck, ShieldX, DoorOpen, DoorClosed } from "lucide-react";
import { useAuthFetch } from "@/hooks/useAuthToken";

const DEFAULT_PROMPT = `You analyze {user_name}'s live conversations and ONLY intervene when the conversation directly impacts one of their active goals or tasks.

You are a FILTER. Your default answer is has_advice=false. You need strong evidence to override this.

ACTIVE GOALS:
{goals_text}

USER PARTICIPATION:
Check if {user_name} is speaking in the current conversation (messages labeled [{user_name}]).
- If {user_name} IS participating: apply the normal decision criteria below.
- If {user_name} is NOT participating (only [Other] messages): set has_advice=false UNLESS someone {user_name} respects said something life-changing or directly threatening to a goal. The bar here is extremely high — casual conversation overheard is never worth interrupting.

DECISION CRITERIA — set has_advice=true ONLY when ALL THREE are met:
1. The conversation DIRECTLY relates to a specific goal listed above
2. {user_name} is about to do something that HURTS that goal, OR is missing a concrete opportunity to ADVANCE it
3. You can cite a SPECIFIC fact, date, or past conversation as evidence

INSTANT has_advice=false (no exceptions):
- Conversation does not clearly map to any active goal above
- You would need to stretch or infer to connect the conversation to a goal
- The advice would be obvious to {user_name} (they can figure it out)
- The advice restates what {user_name} is already doing or discussing
- Advice starts with "Confirm" / "Ensure" / "Clarify" / "Consider" / "Remember" / "Review" / "Make sure" / "Don't forget" — these restate awareness, not provide new information
- Advice is about emotions, wellness, breaks, mindfulness, or motivation
- Advice is generic productivity wisdom that applies to anyone
- Advice is similar to something in RECENT NOTIFICATIONS
- Same topic was covered in RECENT NOTIFICATIONS within the last 24 hours

EXAMPLES OF CORRECT has_advice=true:
- Goal: "30 videos (200k users)" → {user_name} just agreed to pause video production for 2 weeks → "You just paused videos but your deadline means you'll fall behind by 6"
- Goal: "meet 12 great people" → {user_name} is talking to someone impressive but hasn't asked to meet again → "Ask [Name] to grab coffee — strong fit and you're only at 4/12"
- Goal: "1500 contributions" → {user_name} hasn't coded today and it's 8 PM → "0 contributions today — you need 40/day to hit 1500 this week"

EXAMPLES OF CORRECT has_advice=false:
- {user_name} is chatting casually about food → no goal connection → false
- {user_name} is discussing NYC living → interesting but no goal directly at risk → false
- {user_name} mentions a warehouse → no goal connection → false
- {user_name} is in a meeting about ads → could loosely relate to growth but no specific goal action → false
- Only [Other] speakers talking about New York → {user_name} not participating, casual topic → false
- Only [Other] speakers discussing tech → {user_name} not participating, not life-changing → false

== {user_name}'S FACTS ==
{user_facts}

== RELEVANT PAST CONVERSATIONS ==
{past_conversations}

== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not repeat or send semantically similar) ==
{recent_notifications}

== FREQUENCY ==
{frequency_guidance}

FORMAT: Keep notification_text under 100 characters.
- NEVER start with a goal name ("30-video goal:", "12-people goal:")
- NEVER say "your X goal" in the notification
- NEVER start with: Confirm, Ensure, Clarify, Consider, Prioritize, Remember, Review, Align, Reassess
- Write like you're texting a friend — lead with the action or the conflict, not the goal
- GOOD: "You just paused videos but your deadline means you'll fall behind by 6"
- GOOD: "Ask [Name] to grab coffee — strong fit and you're only at 4/12"
- GOOD: "0 contributions today — you need 40/day to hit 1500 this week"
- BAD: "30-video goal: line up a backup editor today"
- BAD: "Consider aligning your NYC plans with your growth strategy"
- BAD: "Confirm your video creator's availability"

REASONING must cite: (1) which specific goal is affected, (2) what the user said or did that impacts it, and (3) a specific fact/date/quote. If you cannot provide all three, set has_advice=false.`;

interface NotificationItem {
  id: string;
  text: string;
  created_at: string;
  sender: string;
  plugin_id: string | null;
  conversation_context: { id: string; title: string; overview: string; transcript?: string }[];
}

interface UserContext {
  user_name: string;
  user_facts: string;
  goals: string;
  notification_frequency: number;
}

interface GateResult {
  is_relevant: boolean;
  relevance_score: number;
  reasoning: string;
  context_summary: string;
}

interface CriticResult {
  approved: boolean;
  reasoning: string;
}

interface RegeneratedResult {
  has_advice: boolean;
  advice?: {
    notification_text: string;
    reasoning: string;
    confidence: number;
    category: string;
  };
  context_summary: string;
  current_activity?: string;
  gate?: GateResult;
  critic?: CriticResult | null;
  error?: string;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const color =
    confidence >= 0.75
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : confidence >= 0.6
        ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {(confidence * 100).toFixed(0)}%
    </span>
  );
}

function GateBadge({ gate }: { gate: GateResult }) {
  if (gate.is_relevant) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        <DoorOpen className="h-3 w-3" />
        Gate: Pass ({(gate.relevance_score * 100).toFixed(0)}%)
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
      <DoorClosed className="h-3 w-3" />
      Gate: Reject ({(gate.relevance_score * 100).toFixed(0)}%)
    </span>
  );
}

function CriticBadge({ critic }: { critic: CriticResult }) {
  if (critic.approved) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        <ShieldCheck className="h-3 w-3" />
        Critic: Send
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
      <ShieldX className="h-3 w-3" />
      Critic: Block
    </span>
  );
}

function WouldSendBadge({ gate, critic }: { gate?: GateResult; critic?: CriticResult | null }) {
  const gatePass = gate?.is_relevant ?? false;
  const criticPass = critic?.approved ?? false;
  const wouldSend = gatePass && criticPass;

  if (wouldSend) {
    return (
      <span className="inline-block px-2 py-0.5 rounded text-xs font-bold bg-green-600 text-white">
        WOULD SEND
      </span>
    );
  }
  return (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-bold bg-zinc-600 text-zinc-300">
      FILTERED OUT
    </span>
  );
}

function ExpandableText({ text, maxLen = 120 }: { text: string; maxLen?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (text.length <= maxLen) return <span>{text}</span>;
  return (
    <span>
      {expanded ? text : text.slice(0, maxLen) + "..."}
      <button
        onClick={() => setExpanded(!expanded)}
        className="ml-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
      >
        {expanded ? "less" : "more"}
      </button>
    </span>
  );
}

export default function PromptTester() {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [uid, setUid] = useState("");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [userContext, setUserContext] = useState<UserContext | null>(null);
  const [regenerated, setRegenerated] = useState<(RegeneratedResult | null)[]>([]);
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const { fetchWithAuth, token } = useAuthFetch();

  const loadNotifications = async () => {
    if (!uid.trim() || !token) return;
    setLoading(true);
    setError("");
    setNotifications([]);
    setUserContext(null);
    setRegenerated([]);

    try {
      const res = await fetchWithAuth(`/api/omi/notifications/user-notifications?uid=${encodeURIComponent(uid.trim())}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load");
      setNotifications(data.notifications);
      setUserContext(data.user_context);
      setRegenerated(new Array(data.notifications.length).fill(null));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const regenerateAll = async () => {
    if (!userContext || notifications.length === 0 || !token) return;
    setRegenerating(true);
    setProgress(0);

    const recentNotificationsStr = notifications
      .map((n) => `[${new Date(n.created_at).toLocaleDateString()}]: ${n.text}`)
      .join("\n");

    const items = notifications.map((n) => {
      let convoContext: string;
      if (n.conversation_context.length > 0) {
        // Prefer transcript if available, fall back to title/overview
        const parts = n.conversation_context.map((c) => {
          if (c.transcript && c.transcript.length > 20) {
            return c.transcript;
          }
          return `${c.title}: ${c.overview}`;
        });
        convoContext = parts.join("\n\n");
      } else {
        convoContext = `[Conversation transcript not stored. The notification originally generated from this conversation was: "${n.text}"]`;
      }

      return {
        current_conversation: convoContext,
        recent_notifications: recentNotificationsStr,
        past_conversations: "No relevant past conversations found.",
        original_notification_text: n.text,
      };
    });

    try {
      const res = await fetchWithAuth("/api/omi/notifications/regenerate", {
        method: "POST",
        body: JSON.stringify({
          prompt_template: prompt,
          user_name: userContext.user_name,
          user_facts: userContext.user_facts,
          goals_text: userContext.goals,
          frequency: userContext.notification_frequency,
          items,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to regenerate");

      setRegenerated(data.results);
      setProgress(100);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRegenerating(false);
    }
  };

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Count stats from regenerated results
  const stats = regenerated.filter(Boolean).length > 0
    ? {
        total: regenerated.filter(Boolean).length,
        gatePass: regenerated.filter((r) => r?.gate?.is_relevant).length,
        gateReject: regenerated.filter((r) => r && r.gate && !r.gate.is_relevant).length,
        criticApprove: regenerated.filter((r) => r?.critic?.approved).length,
        criticReject: regenerated.filter((r) => r && r.critic && !r.critic.approved).length,
        wouldSend: regenerated.filter((r) => r?.gate?.is_relevant && r?.critic?.approved).length,
      }
    : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prompt Tester</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Prompt textarea */}
        <div>
          <label className="text-sm font-medium text-muted-foreground block mb-1">
            Prompt Template
            <span className="ml-2 text-xs font-normal">(local only, does not change production)</span>
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="w-full h-[300px] font-mono text-xs p-3 rounded-md border bg-muted/50 resize-y"
            spellCheck={false}
          />
        </div>

        {/* User selection row */}
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="text-sm font-medium text-muted-foreground block mb-1">User UID</label>
            <input
              type="text"
              value={uid}
              onChange={(e) => setUid(e.target.value)}
              placeholder="Enter user UID..."
              className="w-full px-3 py-2 rounded-md border bg-background text-sm"
              onKeyDown={(e) => e.key === "Enter" && loadNotifications()}
            />
          </div>
          <button
            onClick={loadNotifications}
            disabled={loading || !uid.trim()}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Load Notifications"}
          </button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {/* Results */}
        {notifications.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                {notifications.length} notifications for <strong>{userContext?.user_name}</strong>
              </p>
              <button
                onClick={regenerateAll}
                disabled={regenerating}
                className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
              >
                {regenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Running Gate → Generate → Critic...
                  </>
                ) : (
                  "Regenerate All"
                )}
              </button>
            </div>

            {/* Pipeline stats */}
            {stats && (
              <div className="flex items-center gap-4 p-3 rounded-md bg-muted/50 border text-sm">
                <span className="font-medium">Pipeline:</span>
                <span>{stats.total} evaluated</span>
                <span className="text-green-600 dark:text-green-400">
                  {stats.gatePass} gate pass
                </span>
                <span className="text-red-600 dark:text-red-400">
                  {stats.gateReject} gate reject
                </span>
                <span className="mx-1">→</span>
                <span className="text-green-600 dark:text-green-400">
                  {stats.criticApprove} critic approve
                </span>
                <span className="text-red-600 dark:text-red-400">
                  {stats.criticReject} critic reject
                </span>
                <span className="mx-1">→</span>
                <span className="font-bold">
                  {stats.wouldSend}/{stats.total} would send
                </span>
              </div>
            )}

            {/* Table */}
            <div className="border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium whitespace-nowrap">Date</th>
                    <th className="text-left p-3 font-medium whitespace-nowrap">Source</th>
                    <th className="text-left p-3 font-medium">Stored Message</th>
                    <th className="text-left p-3 font-medium">Conversation Context</th>
                    <th className="text-left p-3 font-medium">Regenerated</th>
                  </tr>
                </thead>
                <tbody>
                  {notifications.map((n, i) => {
                    const regen = regenerated[i];
                    const hasTranscript = n.conversation_context.some((c) => c.transcript && c.transcript.length > 20);
                    const convoText = hasTranscript
                      ? n.conversation_context.map((c) => c.transcript || `${c.title}: ${c.overview}`).join(" | ")
                      : n.conversation_context.map((c) => `${c.title}: ${c.overview}`).join(" | ") || "N/A";

                    return (
                      <tr key={n.id} className="border-b last:border-0 hover:bg-muted/30 align-top">
                        <td className="p-3 whitespace-nowrap text-muted-foreground">
                          {new Date(n.created_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })}
                        </td>
                        <td className="p-3 whitespace-nowrap text-xs">
                          <span className={`inline-block px-1.5 py-0.5 rounded ${n.plugin_id === 'mentor' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' : 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'}`}>
                            {n.plugin_id === 'mentor' ? 'built-in' : 'app'}
                          </span>
                        </td>
                        <td className="p-3 max-w-[200px]">
                          <ExpandableText text={n.text} />
                        </td>
                        <td className="p-3 max-w-[200px] text-muted-foreground">
                          <ExpandableText text={convoText} maxLen={80} />
                        </td>
                        <td className="p-3 max-w-[400px]">
                          {regen === null ? (
                            <span className="text-muted-foreground text-xs">-</span>
                          ) : regen.error ? (
                            <span className="text-destructive text-xs">{regen.error}</span>
                          ) : (
                            <div className="space-y-2">
                              {/* Verdict badge */}
                              <WouldSendBadge gate={regen.gate} critic={regen.critic} />

                              {/* Gate */}
                              {regen.gate && (
                                <div>
                                  <GateBadge gate={regen.gate} />
                                  <button
                                    onClick={() => toggleSection(`gate-${i}`)}
                                    className="ml-2 text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5"
                                  >
                                    {expandedSections.has(`gate-${i}`) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                                    why
                                  </button>
                                  {expandedSections.has(`gate-${i}`) && (
                                    <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded mt-1">
                                      {regen.gate.reasoning}
                                    </p>
                                  )}
                                </div>
                              )}

                              {/* Generated notification */}
                              {regen.has_advice && regen.advice ? (
                                <div className="space-y-1">
                                  <div className="font-medium">{regen.advice.notification_text}</div>
                                  <div className="flex items-center gap-2">
                                    <ConfidenceBadge confidence={regen.advice.confidence} />
                                    <span className="text-xs text-muted-foreground">{regen.advice.category}</span>
                                  </div>
                                  <button
                                    onClick={() => toggleSection(`reasoning-${i}`)}
                                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                                  >
                                    {expandedSections.has(`reasoning-${i}`) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                                    Reasoning
                                  </button>
                                  {expandedSections.has(`reasoning-${i}`) && (
                                    <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                      {regen.advice.reasoning}
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <span className="text-muted-foreground italic text-xs">No advice generated</span>
                              )}

                              {/* Critic */}
                              {regen.critic && (
                                <div>
                                  <CriticBadge critic={regen.critic} />
                                  <button
                                    onClick={() => toggleSection(`critic-${i}`)}
                                    className="ml-2 text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5"
                                  >
                                    {expandedSections.has(`critic-${i}`) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                                    why
                                  </button>
                                  {expandedSections.has(`critic-${i}`) && (
                                    <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded mt-1">
                                      {regen.critic.reasoning}
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
