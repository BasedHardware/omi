'use client';

import { use } from 'react';
import { motion } from 'framer-motion';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { ConversationDetail } from '@/components/conversations/ConversationDetail';
import { useConversation } from '@/hooks/useConversation';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';

interface ConversationPageProps {
  params: Promise<{ id: string }>;
}

function ConversationDetailSkeleton() {
  return (
    <div className="max-w-4xl mx-auto animate-pulse">
      {/* Back button skeleton */}
      <div className="h-5 w-40 bg-bg-tertiary rounded mb-6" />

      {/* Header skeleton */}
      <div className="flex items-start gap-4 mb-8">
        <div className="w-16 h-16 rounded-2xl bg-bg-tertiary" />
        <div className="flex-1">
          <div className="h-8 w-3/4 bg-bg-tertiary rounded mb-3" />
          <div className="flex gap-4">
            <div className="h-4 w-32 bg-bg-tertiary rounded" />
            <div className="h-4 w-24 bg-bg-tertiary rounded" />
            <div className="h-4 w-20 bg-bg-tertiary rounded" />
          </div>
        </div>
      </div>

      {/* Summary skeleton */}
      <div className="mb-8">
        <div className="h-6 w-32 bg-bg-tertiary rounded mb-4" />
        <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary">
          <div className="space-y-2">
            <div className="h-4 w-full bg-bg-tertiary rounded" />
            <div className="h-4 w-5/6 bg-bg-tertiary rounded" />
            <div className="h-4 w-4/6 bg-bg-tertiary rounded" />
          </div>
        </div>
      </div>

      {/* Transcript skeleton */}
      <div>
        <div className="h-6 w-40 bg-bg-tertiary rounded mb-4" />
        <div className="p-4 rounded-xl bg-bg-secondary border border-bg-tertiary space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-4 rounded-xl bg-bg-tertiary">
              <div className="flex justify-between mb-2">
                <div className="h-4 w-20 bg-bg-quaternary rounded" />
                <div className="h-4 w-16 bg-bg-quaternary rounded" />
              </div>
              <div className="space-y-2">
                <div className="h-4 w-full bg-bg-quaternary rounded" />
                <div className="h-4 w-3/4 bg-bg-quaternary rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ConversationPageContent({ params }: ConversationPageProps) {
  const { id } = use(params);
  const { user } = useAuth();
  const { conversation, loading, error, update: updateConversation } = useConversation(id);

  return (
    <MainLayout>
      <div className="p-4 md:p-6 lg:p-8">
        {loading && <ConversationDetailSkeleton />}

        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={cn(
              'max-w-4xl mx-auto p-6 rounded-xl',
              'bg-error/10 border border-error/20',
              'text-error text-center'
            )}
          >
            <p className="font-medium mb-2">Failed to load conversation</p>
            <p className="text-sm opacity-80">{error}</p>
          </motion.div>
        )}

        {!loading && !error && conversation && (
          <ConversationDetail
            conversation={conversation}
            userName={user?.displayName || undefined}
            onConversationUpdate={updateConversation}
          />
        )}

        {!loading && !error && !conversation && (
          <div className="max-w-4xl mx-auto text-center py-12 text-text-tertiary">
            <p>Conversation not found</p>
          </div>
        )}
      </div>
    </MainLayout>
  );
}

export default function ConversationPage(props: ConversationPageProps) {
  return (
    <ProtectedRoute>
      <ConversationPageContent {...props} />
    </ProtectedRoute>
  );
}
