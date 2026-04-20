'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Loader2, Mic, Play, RotateCcw, Send } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { Message } from '@/types/chat';
import {
  getRoleplayScenarioById,
  ROLEPLAY_DIFFICULTIES,
  SALES_ROLEPLAY_SCENARIOS,
  type RoleplayDifficulty,
} from '@/lib/sales-roleplay';

const SESSION_START_MESSAGE =
  'Begin the live role-play now. Open as the buyer with a short first line that naturally starts the call.';

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
  const scrollRef = useRef<HTMLDivElement>(null);

  const scenario = useMemo(
    () => getRoleplayScenarioById(scenarioId) ?? SALES_ROLEPLAY_SCENARIOS[0],
    [scenarioId],
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
  }, [messages, typingMessage, scrollToBottom]);

  const streamRoleplayTurn = useCallback(
    async (message: string, history: Message[]) => {
      setIsLoading(true);

      try {
        const response = await fetch('/api/roleplay', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message,
            scenarioId: scenario.id,
            difficulty,
            repObjective,
            conversationHistory: history,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No reader available');
        }

        let accumulatedText = '';
        const typingId = Date.now();

        setTypingMessage({
          id: typingId,
          text: '',
          sender: 'omi',
          type: 'text',
          status: 'sending',
        });

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = new TextDecoder().decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6);
            if (data === '[DONE]') continue;

            try {
              const parsed = JSON.parse(data);
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
          }
        }

        setTypingMessage(null);

        if (accumulatedText) {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now(),
              text: accumulatedText,
              sender: 'omi',
              type: 'text',
              status: 'received',
            },
          ]);
        }
      } finally {
        setIsLoading(false);
      }
    },
    [difficulty, repObjective, scenario.id],
  );

  const handleStartSession = async () => {
    setMessages([]);
    setTypingMessage(null);
    setSessionStarted(true);
    await streamRoleplayTurn(SESSION_START_MESSAGE, []);
  };

  const handleSendMessage = async () => {
    if (!inputText.trim() || isLoading || !sessionStarted) return;

    const userMessage: Message = {
      id: Date.now(),
      text: inputText.trim(),
      sender: 'user',
      type: 'text',
      status: 'sent',
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputText('');
    await streamRoleplayTurn(userMessage.text, messages);
  };

  const handleReset = () => {
    setMessages([]);
    setTypingMessage(null);
    setInputText('');
    setSessionStarted(false);
    setIsLoading(false);
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
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

          <Card className="border-zinc-800 bg-zinc-900/80 text-white">
            <CardHeader>
              <CardTitle className="text-2xl">Sales Role-Play</CardTitle>
              <CardDescription className="text-zinc-400">
                Run a live buyer simulation with preset scenarios, objections, and difficulty levels.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <div className="text-sm font-medium text-zinc-300">Scenario</div>
                <div className="space-y-3">
                  {SALES_ROLEPLAY_SCENARIOS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setScenarioId(item.id)}
                      className={`w-full rounded-xl border p-4 text-left transition ${
                        item.id === scenario.id
                          ? 'border-white bg-white text-black'
                          : 'border-zinc-800 bg-zinc-950 hover:border-zinc-700'
                      }`}
                    >
                      <div className="font-medium">{item.title}</div>
                      <div className={`mt-1 text-sm ${item.id === scenario.id ? 'text-zinc-700' : 'text-zinc-400'}`}>
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
                      className={difficulty === item.id ? '' : 'border-zinc-700 bg-zinc-950 text-zinc-300 hover:bg-zinc-900'}
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
                  className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-zinc-600"
                  placeholder="What should the rep practice in this session?"
                />
              </div>

              <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950 p-4">
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
                    Likely Objections
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
              </div>

              <div className="flex gap-2">
                <Button onClick={handleStartSession} disabled={isLoading} className="flex-1">
                  {isLoading && !sessionStarted ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  Start Live Session
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

        <section className="flex min-h-[70vh] flex-1 flex-col rounded-2xl border border-zinc-800 bg-zinc-900/70">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
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
            <Badge variant="outline" className="border-zinc-700 text-zinc-300">
              <Mic className="mr-1 h-3.5 w-3.5" />
              Live buyer
            </Badge>
          </div>

          <ScrollArea ref={scrollRef} className="flex-1 px-4 py-5">
            <div className="mx-auto flex max-w-3xl flex-col gap-4">
              {!sessionStarted && (
                <Card className="border-dashed border-zinc-700 bg-zinc-950 text-white">
                  <CardContent className="pt-6 text-sm text-zinc-400">
                    Start the session to let the buyer open the call. Then respond like a live rep.
                  </CardContent>
                </Card>
              )}

              {messages.map((message) => {
                const isUser = message.sender === 'user';
                return (
                  <div
                    key={message.id}
                    className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${
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
                  <div className="max-w-[85%] rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm leading-6 text-zinc-100">
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
            <div className="mx-auto flex max-w-3xl gap-3">
              <Input
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    handleSendMessage();
                  }
                }}
                disabled={!sessionStarted || isLoading}
                placeholder={
                  sessionStarted
                    ? 'Respond as the rep...'
                    : 'Start a session before sending a reply'
                }
                className="border-zinc-800 bg-zinc-950 text-white placeholder:text-zinc-500"
              />
              <Button onClick={handleSendMessage} disabled={!sessionStarted || isLoading || !inputText.trim()}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
