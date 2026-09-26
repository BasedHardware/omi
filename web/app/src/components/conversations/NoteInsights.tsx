'use client';

import { Brain, History, Sparkles, Target, User } from 'lucide-react';
import type { NoteInsight, NoteInsightKind } from '@/types/conversation';

const KIND_ICONS: Record<NoteInsightKind, typeof Sparkles> = {
  prior_meeting: History,
  goal: Target,
  memory: Brain,
  person: User,
};

interface NoteInsightsProps {
  insights?: NoteInsight[] | null;
}

export function NoteInsights({ insights }: NoteInsightsProps) {
  const items = (insights ?? []).filter(
    (insight) => typeof insight?.text === 'string' && insight.text.trim(),
  );
  if (items.length === 0) return null;

  return (
    <div className="mb-5 rounded-xl border border-bg-quaternary/50 bg-bg-tertiary/50 p-3.5">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-quaternary">
        For you · only visible to you
      </p>
      <ul className="space-y-1.5">
        {items.map((insight, index) => {
          const Icon = (insight.kind && KIND_ICONS[insight.kind]) || Sparkles;
          return (
            <li
              key={index}
              className="flex items-center gap-2 text-sm text-text-secondary"
            >
              <Icon className="h-3.5 w-3.5 flex-shrink-0 text-text-tertiary" />
              <span className="truncate">{insight.text!.trim()}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
