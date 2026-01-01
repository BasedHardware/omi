'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { TaskHub } from '@/components/tasks/TaskHub';

function TasksContent() {
  return (
    <MainLayout title="Tasks">
      <TaskHub />
    </MainLayout>
  );
}

export default function TasksPage() {
  return (
    <ProtectedRoute>
      <TasksContent />
    </ProtectedRoute>
  );
}
