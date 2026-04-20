'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Loader2,
  Mic,
  Play,
  RotateCcw,
  Send,
  Sparkles,
} from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  getRoleplayScenarioById,
  ROLEPLAY_DIFFICULTIES,
  SALES_ROLEPLAY_SCENARIOS,
  type RoleplayDifficulty,
  type RoleplayScorecard,
} from '@/lib/sales-roleplay';
import type { Message } from '@/types/chat';

const SESSION_START_MESSAGE =
  'Begin the live role-play now. Open as the buyer with a short first line that naturally starts the call.';

const formatElapsedTime = (totalSeconds: number) => {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};

const getScoreTone = (score: number) => {
  if (score >= 85) {
    return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100';
  }
  if (score >= 70) {
    return 'border-amber-500/40 bg-amber-500/10 text-amber-100';
  }
  return 'border-rose-500/40 bg-rose-500/10 text-rose-100';
};

export default function SalesRoleplayPage() {
  const [scenarioId, setScenarioId] = useState(SALES_ROLEPLAY_SCENARIOS[0].id);
  const [difficulty, setDifficulty] = useState<RoleplayDifficulty>('medium');
  const [repObjective, setRepObjective] = useState(
    'Practice discovery, objection handling, and securing a concrete next step.',
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [typingMessage, setTypingMessage] = useState<Message | null>(null);
  const [inputText, setInputText] = useState('');
  const [sessionStarted, setSessionStarted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isScoring, setIsScoring] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [scorecard, setScorecard] = useState<RoleplayScorecard | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scenario = useMemo(
    () => getRoleplayScenarioById(scenarioId) ?? SALES_ROLEPLAY_SCENARIOS[0],
    [scenarioId],
  );

  const sessionIsComplete = Boolean(scorecard);
  const sessionIsLive = sessionStarted && !sessionIsComplete;
  const repTurns = useMemo(
    () => messages.filter((message) => message.sender === 'user').length,
    [messages],
  );
  const buyerTurns = useMemo(
    () => messages.filter((message) => message.sender === 'omi').length,
    [messages],
  );

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, typingMessage, scorecard, scrollToBottom]);

  useEffect(() => {
    if (!sessionIsLive || !startedAt) {
      return;
    }

    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));

    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);

    return () => window.clearInterval(interval);
  }, [sessionIsLive, startedAt]);

  const streamRoleplayTurn = useCallback(
    async (message: string, history: Message[]) => {
      setIsLoading(true);
      setErrorMessage(null);
      setTypingMessage(null);

      try {
        const response = await fetch('/api/roleplay', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: 'roleplay',
            message,
            scenarioId: scenario.id,
            difficulty,
            repObjective,
            conversationHistory: history,
          }),
        });

        if (!response.ok) {
          const errorPayload = await response.json().catch(() => null);
          throw new Error(
            errorPayload?.message ||
              errorPayload?.details ||
              `Role-play request failed with HTTP ${response.status}.`,
          );
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('Live stream was unavailable for this session.');
        }

        const decoder = new TextDecoder();
        let accumulatedText = '';
        let buffer = '';
        const typingId = Date.now();

        setTypingMessage({
          id: typingId,
          text: '',
          sender: 'omi',
          type: 'text',
          status: 'sending',
        });

        const flushLine = (line: string) => {
          if (!line.startsWith('data: ')) return;

          const data = line.slice(6);
          if (!data || data === '[DONE]') return;

          try {
            const parsed = JSON.parse(data) as { text?: string };
            if (parsed.text) {
              accumulatedText += parsed.text;
              setTypingMessage({
                id: typingId,
                text: accumulatedText,
                sender: 'omi',
                type: 'text',
                status: 'sending',
              });
            }
          } catch (error) {
            console.warn('Failed to parse SSE message:', error);
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            flushLine(line.trim());
          }
        }

        const trailingLine = buffer.trim();
        if (trailingLine) {
          flushLine(trailingLine);
        }

        setTypingMessage(null);

        if (!accumulatedText.trim()) {
          throw new Error('The buyer did not return a usable response.');
        }

        const buyerMessage: Message = {
          id: Date.now(),
          text: accumulatedText.trim(),
          sender: 'omi',
          type: 'text',
          status: 'received',
        };

        setMessages((prev) => [...prev, buyerMessage]);
        return buyerMessage;
      } catch (error) {
        setTypingMessage(null);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to reach the live buyer right now. Try again in a moment.',
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [difficulty, repObjective, scenario.id],
  );

  const handleStartSession = async () => {
    setMessages([]);
    setTypingMessage(null);
    setInputText('');
    setSessionStarted(false);
    setScorecard(null);
    setStartedAt(null);
    setElapsedSeconds(0);
    setErrorMessage(null);

    const buyerOpening = await streamRoleplayTurn(SESSION_START_MESSAGE, []);
    if (buyerOpening) {
      setSessionStarted(true);
      setStartedAt(Date.now());
    }
  };

  const handleSendMessage = async () => {
    if (!inputText.trim() || isLoading || !sessionIsLive) return;

    const userMessage: Message = {
      id: Date.now(),
      text: inputText.trim(),
      sender: 'user',
      type: 'text',
      status: 'sent',
    };

    const nextHistory = [...messages, userMessage];
    setMessages((prev) => [...prev, userMessage]);
    setInputText('');
    await streamRoleplayTurn(userMessage.text, nextHistory);
  };

  const handleGenerateScorecard = async () => {
    if (!sessionStarted || repTurns === 0 || isLoading || isScoring) return;

    setIsScoring(true);
    setErrorMessage(null);

    try {
      const response = await fetch('/api/roleplay', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'scorecard',
          scenarioId: scenario.id,
          difficulty,
          repObjective,
          conversationHistory: messages,
        }),
      });

      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          payload?.message ||
            payload?.details ||
            `Scorecard request failed with HTTP ${response.status}.`,
        );
      }

      setScorecard(payload?.scorecard ?? null);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to generate the scorecard right now. Try again in a moment.',
      );
    } finally {
      setIsScoring(false);
    }
  };

  const handleReset = () => {
    setMessages([]);
    setTypingMessage(null);
    setInputText('');
    setSessionStarted(false);
    setIsLoading(false);
    setIsScoring(false);
    setErrorMessage(null);
    setScorecard(null);
    setStartedAt(null);
    setElapsedSeconds(0);
  };

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,197,94,0.18),_transparent_28%),linear-gradient(180deg,_#09090b_0%,_#111827_100%)] text-white">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-6 lg:flex-row">
        <section className="w-full lg:max-w-sm">
          <div className="mb-4 flex items-center justify-between">
            <Link href="/" className="inline-flex items-center gap-2 text-sm text-zinc-400 hover:text-white">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
            <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-200">
              Live MVP
            </Badge>
          </div>

          <Card className="border-zinc-800/80 bg-zinc-950/80 text-white shadow-2xl shadow-black/20 backdrop-blur">
            <CardHeader>
              <CardTitle className="text-2xl">Sales Role-Play</CardTitle>
              <CardDescription className="text-zinc-400">
                Run a live buyer simulation, stay in the call, then get a coaching scorecard on the transcript.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3">
                  <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Status</div>
                  <div className="mt-2 text-sm font-medium">
                    {sessionIsComplete ? 'Reviewed' : sessionIsLive ? 'Live call' : 'Ready'}
                  </div>
                </div>
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3">
                  <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Turns</div>
                  <div className="mt-2 text-sm font-medium">{repTurns + buyerTurns}</div>
                </div>
                <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-3">
                  <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Timer</div>
                  <div className="mt-2 text-sm font-medium">{formatElapsedTime(elapsedSeconds)}</div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="text-sm font-medium text-zinc-300">Scenario</div>
                <div className="space-y-3">
                  {SALES_ROLEPLAY_SCENARIOS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setScenarioId(item.id)}
                      disabled={isLoading || isScoring}
                      className={`w-full rounded-2xl border p-4 text-left transition ${
                        item.id === scenario.id
                          ? 'border-emerald-400/70 bg-emerald-50 text-zinc-950'
                          : 'border-zinc-800 bg-zinc-950/80 hover:border-zinc-700'
                      }`}
                    >
                      <div className="font-medium">{item.title}</div>
                      <div
                        className={`mt-1 text-sm ${
                          item.id === scenario.id ? 'text-zinc-700' : 'text-zinc-400'
                        }`}
                      >
                        {item.summary}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <div className="text-sm font-medium text-zinc-300">Difficulty</div>
                <div className="grid grid-cols-3 gap-2">
                  {ROLEPLAY_DIFFICULTIES.map((item) => (
                    <Button
                      key={item.id}
                      variant={difficulty === item.id ? 'default' : 'outline'}
                      className={
                        difficulty === item.id
                          ? 'bg-white text-black hover:bg-zinc-200'
                          : 'border-zinc-700 bg-zinc-950 text-zinc-300 hover:bg-zinc-900'
                      }
                      disabled={isLoading || isScoring}
                      onClick={() => setDifficulty(item.id)}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
                <p className="text-sm text-zinc-400">
                  {ROLEPLAY_DIFFICULTIES.find((item) => item.id === difficulty)?.description}
                </p>
              </div>

              <div className="space-y-3">
                <label className="text-sm font-medium text-zinc-300" htmlFor="repObjective">
                  Rep Focus
                </label>
                <textarea
                  id="repObjective"
                  value={repObjective}
                  onChange={(event) => setRepObjective(event.target.value)}
                  rows={4}
                  disabled={isLoading || isScoring}
                  className="w-full rounded-2xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-zinc-600 disabled:cursor-not-allowed disabled:opacity-70"
                  placeholder="What should the rep practice in this session?"
                />
              </div>

              <div className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-950/80 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{scenario.buyerName}</div>
                    <div className="text-sm text-zinc-400">
                      {scenario.buyerRole} at {scenario.company}
                    </div>
                  </div>
                  <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                    {scenario.dealStage}
                  </Badge>
                </div>
                <p className="text-sm text-zinc-400">{scenario.companyContext}</p>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Training goals
                  </div>
                  <div className="space-y-2">
                    {scenario.goals.map((goal) => (
                      <div key={goal} className="rounded-xl border border-zinc-800 bg-zinc-900/70 px-3 py-2 text-sm text-zinc-300">
                        {goal}
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Likely objections
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {scenario.objections.map((objection) => (
                      <Badge
                        key={objection}
                        variant="outline"
                        className="border-zinc-800 bg-zinc-900 text-zinc-300"
                      >
                        {objection}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    What good looks like
                  </div>
                  <div className="space-y-2">
                    {scenario.successSignals.map((signal) => (
                      <div key={signal} className="flex items-start gap-2 text-sm text-zinc-300">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />
                        <span>{signal}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {scorecard && (
                <div className={`rounded-2xl border p-4 ${getScoreTone(scorecard.overallScore)}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] opacity-70">Scorecard</div>
                      <div className="mt-1 text-lg font-semibold">{scorecard.outcome}</div>
                    </div>
                    <div className="text-3xl font-semibold">{scorecard.overallScore}</div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-current/90">{scorecard.summary}</p>
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  onClick={handleStartSession}
                  disabled={isLoading || isScoring}
                  className="flex-1 bg-white text-black hover:bg-zinc-200"
                >
                  {isLoading && !sessionStarted ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {sessionStarted ? 'Restart Session' : 'Start Live Session'}
                </Button>
                <Button
                  variant="outline"
                  className="border-zinc-700 bg-zinc-950 text-zinc-300 hover:bg-zinc-900"
                  onClick={handleReset}
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="flex min-h-[70vh] flex-1 flex-col overflow-hidden rounded-[28px] border border-zinc-800/80 bg-zinc-950/70 shadow-2xl shadow-black/30 backdrop-blur">
          <div className="border-b border-zinc-800 px-5 py-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-3">
                <Avatar className="h-11 w-11 border border-zinc-700">
                  <AvatarFallback className="bg-zinc-800 text-white">
                    {scenario.buyerName.slice(0, 1)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <div className="font-medium">{scenario.buyerName}</div>
                  <div className="text-sm text-zinc-400">
                    {scenario.buyerRole} at {scenario.company}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                  <Mic className="mr-1 h-3.5 w-3.5" />
                  {sessionIsComplete ? 'Buyer transcript captured' : 'Live buyer'}
                </Badge>
                <Badge variant="outline" className="border-zinc-700 text-zinc-300">
                  <Clock3 className="mr-1 h-3.5 w-3.5" />
                  {formatElapsedTime(elapsedSeconds)}
                </Badge>
                <Badge
                  variant="outline"
                  className={
                    sessionIsComplete
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                      : sessionIsLive
                        ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
                        : 'border-zinc-700 text-zinc-300'
                  }
                >
                  {sessionIsComplete ? 'Reviewed' : sessionIsLive ? 'In call' : 'Ready'}
                </Badge>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Goal</div>
                <div className="mt-1 text-sm text-zinc-200">{repObjective}</div>
              </div>
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Scenario</div>
                <div className="mt-1 text-sm text-zinc-200">{scenario.summary}</div>
              </div>
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">Live cue</div>
                <div className="mt-1 text-sm text-zinc-200">{scenario.successSignals[0]}</div>
              </div>
            </div>
          </div>

          <ScrollArea ref={scrollRef} className="flex-1 px-4 py-5">
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {!sessionStarted && (
                <Card className="border-dashed border-zinc-700 bg-zinc-950/80 text-white">
                  <CardContent className="pt-6">
                    <div className="flex items-start gap-3">
                      <Sparkles className="mt-0.5 h-5 w-5 text-emerald-300" />
                      <div>
                        <div className="font-medium">Run it like a real call</div>
                        <p className="mt-1 text-sm leading-6 text-zinc-400">
                          Start the session and the buyer will open the conversation. Ask sharp discovery questions, handle objections directly, and end by securing a concrete next step.
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {errorMessage && (
                <Card className="border-rose-500/30 bg-rose-500/10 text-white">
                  <CardContent className="pt-6 text-sm leading-6 text-rose-100">
                    {errorMessage}
                  </CardContent>
                </Card>
              )}

              {scorecard && (
                <Card className="border-zinc-800 bg-zinc-900/80 text-white">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between text-xl">
                      <span>Post-Session Scorecard</span>
                      <span className="text-2xl">{scorecard.overallScore}/100</span>
                    </CardTitle>
                    <CardDescription className="text-zinc-400">{scorecard.outcome}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-5 text-sm">
                    <p className="leading-6 text-zinc-300">{scorecard.summary}</p>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
                        <div className="mb-3 font-medium text-white">What worked</div>
                        <div className="space-y-2 text-zinc-300">
                          {scorecard.strengths.map((item) => (
                            <div key={item} className="flex items-start gap-2">
                              <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
                        <div className="mb-3 font-medium text-white">Missed opportunities</div>
                        <div className="space-y-2 text-zinc-300">
                          {scorecard.missedOpportunities.map((item) => (
                            <div key={item} className="flex items-start gap-2">
                              <span className="mt-0.5 h-2 w-2 rounded-full bg-amber-400" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
                        <div className="mb-3 font-medium text-white">Buyer signals</div>
                        <div className="space-y-2 text-zinc-300">
                          {scorecard.buyerSignals.map((signal) => (
                            <div key={signal}>{signal}</div>
                          ))}
                        </div>
                      </div>
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
                        <div className="mb-3 font-medium text-white">Coach recommendation</div>
                        <p className="leading-6 text-zinc-300">{scorecard.nextStepAdvice}</p>
                        <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/80 p-3 text-zinc-200">
                          "{scorecard.recommendedNextLine}"
                        </div>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4">
                      <div className="mb-3 font-medium text-white">Goal coverage</div>
                      <div className="space-y-3">
                        {scorecard.goalCoverage.map((item) => (
                          <div key={item.goal} className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3">
                            <div className="flex items-center justify-between gap-3">
                              <div className="font-medium text-zinc-100">{item.goal}</div>
                              <Badge
                                variant="outline"
                                className={
                                  item.status === 'hit'
                                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                                    : item.status === 'partial'
                                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
                                      : 'border-zinc-700 text-zinc-300'
                                }
                              >
                                {item.status}
                              </Badge>
                            </div>
                            <p className="mt-2 text-zinc-400">{item.evidence}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {messages.map((message) => {
                const isUser = message.sender === 'user';
                return (
                  <div key={message.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[85%] rounded-3xl px-4 py-3 text-sm leading-6 shadow-lg shadow-black/10 ${
                        isUser
                          ? 'bg-white text-black'
                          : 'border border-zinc-800 bg-zinc-950 text-zinc-100'
                      }`}
                    >
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-60">
                        {isUser ? 'Rep' : scenario.buyerName}
                      </div>
                      <div className="whitespace-pre-wrap">{message.text}</div>
                    </div>
                  </div>
                );
              })}

              {typingMessage && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-3xl border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm leading-6 text-zinc-100 shadow-lg shadow-black/10">
                    <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-60">
                      {scenario.buyerName}
                    </div>
                    <div className="whitespace-pre-wrap">{typingMessage.text || '...'}</div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="border-t border-zinc-800 px-4 py-4">
            <div className="mx-auto flex max-w-3xl flex-col gap-3 md:flex-row">
              <div className="flex-1 rounded-2xl border border-zinc-800 bg-zinc-950/90 p-3">
                <textarea
                  value={inputText}
                  onChange={(event) => setInputText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  disabled={!sessionIsLive || isLoading || isScoring}
                  placeholder={
                    sessionIsComplete
                      ? 'Reset or restart to run another round.'
                      : sessionStarted
                        ? 'Respond as the rep. Press Enter to send, Shift+Enter for a new line.'
                        : 'Start a session before sending a reply.'
                  }
                  rows={3}
                  className="w-full resize-none border-0 bg-transparent text-sm leading-6 text-white outline-none placeholder:text-zinc-500 disabled:cursor-not-allowed disabled:opacity-70"
                />
                <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
                  <span>{sessionIsLive ? 'Stay concise and commercial.' : 'Transcript will appear above.'}</span>
                  <span>{repTurns} rep turns</span>
                </div>
              </div>

              <div className="flex gap-3 md:w-[220px] md:flex-col">
                <Button
                  onClick={handleSendMessage}
                  disabled={!sessionIsLive || isLoading || isScoring || !inputText.trim()}
                  className="flex-1 bg-white text-black hover:bg-zinc-200"
                >
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Send reply
                </Button>
                <Button
                  variant="outline"
                  onClick={handleGenerateScorecard}
                  disabled={!sessionStarted || repTurns === 0 || isLoading || isScoring || sessionIsComplete}
                  className="flex-1 border-zinc-700 bg-zinc-950 text-zinc-300 hover:bg-zinc-900"
                >
                  {isScoring ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {sessionIsComplete ? 'Scorecard ready' : 'End and score'}
                </Button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
