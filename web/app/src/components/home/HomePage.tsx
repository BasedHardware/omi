'use client';

import { useEffect, useRef, useState } from 'react';
import Image from '@tschk/moonshine-next/image';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Target } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useChat as useChatContext } from '@/components/chat/ChatContext';
import { useGoals } from '@/hooks/useGoals';
import { useHomeTasks } from '@/hooks/useHomeTasks';
import { useScrollEdges } from '@/hooks/useScrollEdges';
import { ChatComposer, type ChatComposerHandle } from '@/components/chat/ChatComposer';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import { RecordingStage } from '@/components/chat/RecordingStage';
import { useGeminiLive } from '@/hooks/useGeminiLive';
import { GoalCard } from './GoalCard';
import { GoalComposer } from './GoalComposer';
import { GoalDetailSheet } from './GoalDetailSheet';
import { HomeTaskList } from './HomeTaskList';
import { cn } from '@/lib/utils';
import type { MessageFile } from '@/types/conversation';

/**
 * Home — the one place Omi answers from.
 *
 * Desktop's Home is a stage with two resting modes (`HomeStagePresentation`):
 * an empty account lands on the hub (greeting, what's waiting on you, the ask
 * bar), and an account with chat history opens straight into the transcript.
 * Chat is not a separate destination on either client; it is what Home becomes
 * once you have said something.
 */

const quickPrompts = [
  'What did I talk about today?',
  'Show my pending tasks',
  'What should I remember?',
  'Summarize my recent conversations',
];

function firstName(displayName: string | null | undefined): string | null {
  const name = displayName?.trim().split(/\s+/)[0];
  return name || null;
}

export function HomePage() {
  const { user } = useAuth();
  // Home renders the same transcript the panel does, so it reads the same
  // selected session rather than pinning itself to the shared thread.
  const { chat, selectedAppId, selectedChatSessionId } = useChatContext();
  const {
    messages,
    isLoading,
    isStreaming,
    streamingText,
    currentThinking,
    error,
    sendMessage,
    loadHistory,
    appendRealtimeExchange,
  } = chat;

  const {
    items: tasks,
    loading: tasksLoading,
    error: tasksError,
    complete: completeTask,
  } = useHomeTasks();
  const {
    goals,
    loading: goalsLoading,
    error: goalsError,
    addGoal,
    editGoal,
    setProgress,
    removeGoal,
  } = useGoals();
  const renameGoal = (id: string, title: string) => editGoal(id, { title });

  const [composerOpen, setComposerOpen] = useState(false);
  const [openGoalId, setOpenGoalId] = useState<string | null>(null);
  const [exchangeStart, setExchangeStart] = useState<number | null>(null);
  const askRef = useRef<ChatComposerHandle>(null);
  const currentsRef = useRef<HTMLDivElement>(null);
  const { ref: scrollRef, edges } = useScrollEdges<HTMLDivElement>();
  const live = useGeminiLive({ messages, onExchange: appendRealtimeExchange });
  const isLive = live.state !== 'idle';
  const loadHistoryRef = useRef(loadHistory);
  loadHistoryRef.current = loadHistory;
  // Launch places Currents in view once. After that the reader owns the
  // scroller: a later no-op loadHistory, a task/goal rerender, or a stream
  // must not scrollIntoView the hub and yank them out of history.
  const readerOwnsViewportRef = useRef(false);

  // Track the goal by id, not by value, so the sheet keeps showing live data
  // after an optimistic write replaces the object.
  const openGoal = goals.find((goal) => goal.id === openGoalId) ?? null;

  useEffect(() => {
    let active = true;
    readerOwnsViewportRef.current = false;
    setExchangeStart(null);
    void loadHistoryRef.current().finally(() => {
      if (!active || readerOwnsViewportRef.current) return;
      window.requestAnimationFrame(() => {
        if (!active || readerOwnsViewportRef.current) return;
        currentsRef.current?.scrollIntoView?.({ block: 'start' });
      });
    });
    return () => {
      active = false;
    };
  }, [selectedAppId, selectedChatSessionId]);

  const markReaderOwned = () => {
    readerOwnsViewportRef.current = true;
  };

  useEffect(() => {
    askRef.current?.focus();
  }, []);

  useEffect(() => {
    document.title = 'Omi - Your AI Companion';
  }, []);

  const handleSend = async (text: string, files: MessageFile[]) => {
    setExchangeStart((current) => current ?? messages.length);
    await sendMessage(
      text,
      files.map((file) => file.id),
      undefined,
      files,
    );
  };

  const name = firstName(user?.displayName);
  const historyMessages =
    exchangeStart === null ? messages : messages.slice(0, exchangeStart);
  const exchangeMessages = exchangeStart === null ? [] : messages.slice(exchangeStart);

  return (
    <div className="flex h-full flex-col">
      {(error || live.error) && (
        <div className="flex-shrink-0 border-b border-error/20 bg-error/10 px-6 py-3">
          <p className="text-sm text-error">{error || live.error}</p>
        </div>
      )}

      {/* The fades belong to the scroll region, not the page: they sit over the
          scroller so messages dissolve into the surface instead of being
          clipped at a hard edge. Each one only appears when there is something
          hidden behind it — a fade over the first or last message is dimming
          content for no reason. */}
      <div className="relative min-h-0 flex-1">
        <div
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute inset-x-0 top-0 z-10 h-24',
            'bg-gradient-to-b from-bg-pane via-bg-pane/80 to-transparent',
            'transition-opacity duration-200',
            edges.atTop ? 'opacity-0' : 'opacity-100',
          )}
        />
        <div
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute inset-x-0 bottom-0 z-10 h-24',
            'bg-gradient-to-t from-bg-pane via-bg-pane/80 to-transparent',
            'transition-opacity duration-200',
            edges.atBottom ? 'opacity-0' : 'opacity-100',
          )}
        />
        <div
          ref={scrollRef}
          className="no-scrollbar h-full overflow-y-auto [overflow-anchor:none]"
          onWheel={markReaderOwned}
          onTouchMove={markReaderOwned}
          onPointerDown={markReaderOwned}
        >
          {isLoading && messages.length === 0 ? (
            <div className="mx-auto max-w-3xl px-4 py-5 sm:px-6 sm:py-6">
              <ChatTranscript
                messages={[]}
                isLoading={isLoading}
                isStreaming={false}
                streamingText=""
                currentThinking=""
              />
            </div>
          ) : (
            <>
              {historyMessages.length > 0 && (
                <section
                  aria-label="Chat history"
                  className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10"
                >
                  <ChatTranscript
                    messages={historyMessages}
                    isLoading={false}
                    isStreaming={false}
                    streamingText=""
                    currentThinking=""
                    autoScroll={false}
                  />
                </section>
              )}
              <motion.section
                ref={currentsRef}
                aria-label="Currents"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
                className={cn(
                  'mx-auto flex max-w-[560px] flex-col items-center justify-center px-4 py-8 sm:px-6 sm:py-12',
                  historyMessages.length > 0
                    ? 'min-h-[calc(100%-14rem)] scroll-mt-56'
                    : 'min-h-full',
                )}
              >
                <Image
                  src="/logo.png"
                  alt="Omi"
                  width={40}
                  height={40}
                  className="rounded-full"
                />
                <h1 className="mt-5 text-center text-2xl font-semibold text-text-primary">
                  {name ? `Hey ${name}. I'm ready.` : "I'm ready."}
                </h1>

                <div className="mt-8 w-full">
                  <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-text-quaternary">
                    Currents
                  </h2>
                  <HomeTaskList
                    items={tasks}
                    loading={tasksLoading}
                    error={tasksError}
                    onComplete={completeTask}
                  />
                </div>

                <div className="mt-8 grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:justify-center">
                  {quickPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => void handleSend(prompt, [])}
                      disabled={isLoading || isStreaming}
                      className={cn(
                        'flex min-h-11 items-center justify-center rounded-full px-3 py-2 text-center text-sm sm:min-h-0 sm:px-4',
                        'border border-stroke bg-bg-tertiary hover:bg-bg-quaternary',
                        'text-text-secondary hover:text-text-primary',
                        'transition-colors',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                      )}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>

                <section className="mt-12 w-full">
                  <header className="flex items-baseline justify-between gap-4">
                    <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-quaternary">
                      Goals
                    </h2>
                    <button
                      type="button"
                      onClick={() => setComposerOpen(true)}
                      className="flex items-center gap-1.5 rounded-element px-2 py-1 text-xs text-text-tertiary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      Set a goal
                    </button>
                  </header>

                  {goalsLoading && goals.length === 0 ? (
                    <div className="mt-4 space-y-3">
                      {[0, 1].map((key) => (
                        <div
                          key={key}
                          className="h-32 animate-pulse rounded-card border border-stroke bg-bg-raised"
                        />
                      ))}
                    </div>
                  ) : goals.length === 0 ? (
                    <button
                      type="button"
                      onClick={() => setComposerOpen(true)}
                      className="mt-4 w-full rounded-card border border-dashed border-stroke bg-bg-raised/40 px-6 py-8 text-center transition-colors hover:bg-bg-raised/70"
                    >
                      <Target className="mx-auto h-6 w-6 text-text-quaternary" />
                      <p className="mt-2 text-sm text-text-quaternary">
                        Set a goal and Omi will track progress against it.
                      </p>
                    </button>
                  ) : (
                    <ul className="mt-4 grid gap-3">
                      {goals.map((goal) => (
                        <GoalCard
                          key={goal.id}
                          goal={goal}
                          onSetProgress={setProgress}
                          onRename={renameGoal}
                          onRemove={removeGoal}
                          onOpen={(selected) => setOpenGoalId(selected.id)}
                        />
                      ))}
                    </ul>
                  )}
                  {goalsError && <p className="mt-3 text-sm text-error">{goalsError}</p>}
                </section>
              </motion.section>
              {(exchangeStart !== null || isStreaming) && (
                <section
                  aria-label="Current chat"
                  className="mx-auto flex min-h-full max-w-3xl flex-col justify-end px-4 py-8 sm:px-6 sm:py-10"
                >
                  <ChatTranscript
                    messages={exchangeMessages}
                    isLoading={false}
                    isStreaming={isStreaming}
                    streamingText={streamingText}
                    currentThinking={currentThinking}
                  />
                </section>
              )}
            </>
          )}
        </div>
      </div>

      {/* The ask bar is the one composer for the whole stage, so it holds its
          position while the content above it changes mode. */}
      <div className="flex-shrink-0 px-4 pb-4 pt-3 sm:px-6 sm:pb-6">
        <div className="mx-auto w-full max-w-[640px] space-y-3 md:max-w-[720px] xl:max-w-[820px]">
          <AnimatePresence>
            {isLive && (
              <RecordingStage
                segments={live.segments}
                duration={live.duration}
                level={live.level}
                isPaused={live.state === 'paused'}
                isInitializing={live.state === 'connecting'}
                onPause={live.pause}
                onResume={live.resume}
                onStop={live.stop}
              />
            )}
          </AnimatePresence>

          <ChatComposer
            ref={askRef}
            onSend={handleSend}
            isStreaming={isStreaming}
            disabled={isLoading}
            appId={selectedAppId ?? undefined}
            placeholder={isLive ? 'Talk with Omi live...' : 'Ask anything...'}
            recording={{
              isActive: isLive,
              level: live.level,
              onStart: () => {
                setExchangeStart((current) => current ?? messages.length);
                void live.start();
              },
              onStop: live.stop,
            }}
          />
        </div>
      </div>

      <GoalComposer
        open={composerOpen}
        onOpenChange={setComposerOpen}
        onCreate={addGoal}
      />

      <GoalDetailSheet
        goal={openGoal}
        onClose={() => setOpenGoalId(null)}
        onSave={editGoal}
      />
    </div>
  );
}
