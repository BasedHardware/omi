'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';

function ConversationsContent() {
  return (
    <MainLayout hideHeader>
      <ConversationSplitView />
    </MainLayout>
  );
}

export default function ConversationsPage() {
  return (
    <ProtectedRoute>
      <ConversationsContent />
    </ProtectedRoute>
  );
}
