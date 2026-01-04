'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { HelpCircle, Lightbulb, ArrowRight, MessageSquare, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UnresolvedQuestion, DecisionMade, KnowledgeNugget } from '@/types/recap';

const MAX_VISIBLE_ITEMS = 3;

interface InsightsSectionProps {
  questions: UnresolvedQuestion[];
  decisions: DecisionMade[];
  learnings: KnowledgeNugget[];
  onConversationClick?: (conversationId: string) => void;
}

export function InsightsSection({
  questions,
  decisions,
  learnings,
  onConversationClick,
}: InsightsSectionProps) {
  const hasContent = questions?.length > 0 || decisions?.length > 0 || learnings?.length > 0;

  if (!hasContent) {
    return null;
  }

  return (
    <div className="flex gap-4">
      {/* Unresolved Questions */}
      <InsightColumn
        title="Questions"
        icon={HelpCircle}
        iconColor="text-warning"
        bgColor="bg-warning/5"
        borderColor="border-warning/20"
        items={questions?.map(q => ({ content: q.question, conversationId: q.conversation_id })) || []}
        onConversationClick={onConversationClick}
      />

      {/* Decisions Made */}
      <InsightColumn
        title="Decisions"
        icon={ArrowRight}
        iconColor="text-success"
        bgColor="bg-success/5"
        borderColor="border-success/20"
        items={decisions?.map(d => ({ content: d.decision, conversationId: d.conversation_id })) || []}
        onConversationClick={onConversationClick}
      />

      {/* Learnings */}
      <InsightColumn
        title="Learnings"
        icon={Lightbulb}
        iconColor="text-purple-primary"
        bgColor="bg-purple-primary/5"
        borderColor="border-purple-primary/20"
        items={learnings?.map(l => ({ content: l.insight, conversationId: l.conversation_id })) || []}
        onConversationClick={onConversationClick}
      />
    </div>
  );
}

interface InsightColumnProps {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  bgColor: string;
  borderColor: string;
  items: Array<{ content: string; conversationId?: string }>;
  onConversationClick?: (conversationId: string) => void;
}

function InsightColumn({
  title,
  icon: Icon,
  iconColor,
  bgColor,
  borderColor,
  items,
  onConversationClick,
}: InsightColumnProps) {
  // Hide empty columns
  if (items.length === 0) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'noise-overlay rounded-xl p-4 flex-1',
        'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
        'border border-white/[0.04]',
        'flex flex-col min-h-[200px]'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/[0.04]">
        <Icon className={cn('w-4 h-4', iconColor)} />
        <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider">
          {title}
        </h4>
      </div>

      {/* Items */}
      <div className="space-y-2 flex-1 overflow-y-auto">
        {items.map((item, idx) => (
          <div
            key={idx}
            className={cn(
              'p-2.5 rounded-lg',
              bgColor,
              'border',
              borderColor
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-text-secondary leading-relaxed flex-1">
                {item.content}
              </p>
              {item.conversationId && (
                <button
                  onClick={() => onConversationClick?.(item.conversationId!)}
                  className={cn(
                    'flex-shrink-0 p-1 rounded',
                    'text-text-tertiary hover:text-purple-primary',
                    'hover:bg-purple-primary/10 transition-colors'
                  )}
                  title="View source conversation"
                >
                  <MessageSquare className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
