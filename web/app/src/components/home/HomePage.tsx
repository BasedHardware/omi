'use client';

import { useEffect, useRef, useState } from 'react';
import Image from '@tschk/moonshine-next/image';
import { motion } from 'framer-motion';
import { Plus, Target, Trash2 } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useChat } from '@/hooks/useChat';
import { useGoals } from '@/hooks/useGoals';
import { useHomeTasks } from '@/hooks/useHomeTasks';
import { ChatComposer, type ChatComposerHandle } from '@/components/chat/ChatComposer';
import { ChatTranscript } from '@/components/chat/ChatTranscript';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { GoalCard } from './GoalCard';
import { GoalComposer } from './GoalComposer';
import { GoalDetailSheet } from './GoalDetailSheet';
import { HomeTaskList } from './HomeTaskList';
import { restingMode } from '@/lib/homeStage';
import { cn } from '@/lib/utils';

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
  const {
    messages,
    isLoading,
    isStreaming,
    streamingText,
    currentThinking,
    error,
    sendMessage,
    clearHistory,
    loadHistory,
  } = useChat();

  const { items: tasks, loading: tasksLoading, complete: completeTask } = useHomeTasks();
  const {
    goals,
    loading: goalsLoading,
    addGoal,
    editGoal,
    setProgress,
    removeGoal,
  } = useGoals();
  const renameGoal = (id: string, title: string) => editGoal(id, { title });

  const [composerOpen, setComposerOpen] = useState(false);
  const [openGoalId, setOpenGoalId] = useState<string | null>(null);
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const askRef = useRef<ChatComposerHandle>(null);

  // Track the goal by id, not by value, so the sheet keeps showing live data
  // after an optimistic write replaces the object.
  const openGoal = goals.find((goal) => goal.id === openGoalId) ?? null;

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    askRef.current?.focus();
  }, []);

  const inChat =
    restingMode({ isLoading, messageCount: messages.length, isStreaming }) === 'chat';

  const handleSend = async (text: string, fileIds: string[]) => {
    await sendMessage(text, fileIds);
  };

  const handleClear = async () => {
    setIsClearing(true);
    try {
      await clearHistory();
      setShowClearDialog(false);
    } finally {
      setIsClearing(false);
    }
  };

  const name = firstName(user?.displayName);

  return (
    <div className="flex h-full flex-col">
      {inChat && (
        <div className="flex flex-shrink-0 items-center justify-end px-6 pt-4">
          <button
            onClick={() => setShowClearDialog(true)}
            className="flex items-center gap-2 rounded-element px-3 py-2 text-text-tertiary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
            title="Clear chat history"
          >
            <Trash2 className="h-4 w-4" />
            <span className="hidden text-sm sm:inline">Clear chat</span>
          </button>
        </div>
      )}

      {error && (
        <div className="flex-shrink-0 border-b border-error/20 bg-error/10 px-6 py-3">
          <p className="text-sm text-error">{error}</p>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {inChat ? (
          <div className="mx-auto max-w-3xl px-6 py-6">
            <ChatTranscript
              messages={messages}
              isLoading={isLoading}
              isStreaming={isStreaming}
              streamingText={streamingText}
              currentThinking={currentThinking}
            />
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="mx-auto flex min-h-full max-w-[560px] flex-col items-center justify-center px-6 py-12"
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
              <HomeTaskList
                items={tasks}
                loading={tasksLoading}
                onComplete={completeTask}
              />
            </div>

            <div className="mt-8 flex flex-wrap justify-center gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => void handleSend(prompt, [])}
                  disabled={isStreaming}
                  className={cn(
                    'rounded-full px-4 py-2 text-sm',
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
                <ul className="mt-4 grid gap-3 sm:grid-cols-2">
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
            </section>
          </motion.div>
        )}
      </div>

      {/* The ask bar is the one composer for the whole stage, so it holds its
          position while the content above it changes mode. */}
      <div className="flex-shrink-0 px-6 pb-6 pt-3">
        <div className="mx-auto max-w-3xl">
          <ChatComposer
            ref={askRef}
            onSend={handleSend}
            isStreaming={isStreaming}
            placeholder={inChat ? 'Ask anything...' : 'Ask Omi anything...'}
            hint={inChat ? 'Press Enter to send, Shift+Enter for new line' : undefined}
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

      <ConfirmDialog
        open={showClearDialog}
        onOpenChange={setShowClearDialog}
        title="Clear chat history?"
        description="This will permanently delete all messages in this conversation. This action cannot be undone."
        confirmLabel="Clear history"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={handleClear}
        isLoading={isClearing}
      />
    </div>
  );
}
