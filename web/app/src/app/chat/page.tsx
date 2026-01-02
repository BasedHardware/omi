'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { FullPageChat } from '@/components/chat/FullPageChat';

function ChatContent() {
  return (
    <MainLayout hideHeader>
      <FullPageChat />
    </MainLayout>
  );
}

export default function ChatPage() {
  return (
    <ProtectedRoute>
      <ChatContent />
    </ProtectedRoute>
  );
}
