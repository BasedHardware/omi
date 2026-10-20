'use client';
import { useEffect, useState } from 'react';
import type { ChatAtCap } from '@/lib/omiApi.generated';
import { PlanStorefrontGate } from '@/lib/planStorefrontGate';
import {
  ContextualPlansSheet,
  useStorefront,
} from '@/components/settings/storefront/StorefrontHost';

export function useChatBudgetPause() {
  const [enabled, setEnabled] = useState(false);
  const [admission, setAdmission] = useState<ChatAtCap | null>(null);
  useEffect(() => {
    let live = true;
    void PlanStorefrontGate.contextualEnabled()
      .then((on) => live && setEnabled(on))
      .catch(() => {
        if (live) setEnabled(false);
      });
    return () => {
      live = false;
    };
  }, []);
  const { data, reload } = useStorefront('web_chat', 'usage_budget', enabled);
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => {
      void reload();
    };
    const rejected = (event: Event) => {
      setAdmission((event as CustomEvent<ChatAtCap>).detail);
      refresh();
    };
    const timer = window.setInterval(refresh, 30000);
    window.addEventListener('focus', refresh);
    window.addEventListener('omi-chat-paused', rejected);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('omi-chat-paused', rejected);
    };
  }, [enabled, reload]);
  useEffect(() => {
    if (data) setAdmission(null);
  }, [data]);
  const state = enabled ? admission ?? data?.chatAtCap ?? null : null;
  return {
    state: state && state.reset_at * 1000 > Date.now() ? state : null,
    data,
    reload,
  };
}

export function ChatPauseCard({
  state,
  onUpgrade,
}: {
  state: ChatAtCap;
  onUpgrade: () => void;
}) {
  return (
    <div
      role="status"
      data-testid="chat-budget-pause"
      className="rounded-2xl border border-stroke bg-bg-tertiary p-4"
    >
      <p className="font-semibold text-text-primary">{state.title}</p>
      <p className="mt-2 text-sm text-text-secondary">{state.body}</p>
      <p className="mt-2 text-sm text-text-primary">{state.reset_line}</p>
      {state.upgrade_label && (
        <button
          className="mt-3 rounded-xl bg-text-primary px-4 py-2 text-sm font-semibold text-bg-primary"
          onClick={onUpgrade}
        >
          {state.upgrade_label}
        </button>
      )}
    </div>
  );
}

export function ChatBudgetPause({
  budget,
}: {
  budget: ReturnType<typeof useChatBudgetPause>;
}) {
  const [open, setOpen] = useState(false);
  if (!budget.state) return null;
  return (
    <>
      <ChatPauseCard state={budget.state} onUpgrade={() => setOpen(true)} />
      <ContextualPlansSheet
        open={open}
        onOpenChange={setOpen}
        source="web_chat"
        trigger="usage_budget"
        initial={budget.data}
        onSubscriptionUpdate={() => {
          void budget.reload();
        }}
      />
    </>
  );
}
