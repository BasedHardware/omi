'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { MemoriesPage } from '@/components/memories/MemoriesPage';

export default function MemoriesRoute() {
  return (
    <ProtectedRoute>
      <MainLayout hideHeader>
        <MemoriesPage />
      </MainLayout>
    </ProtectedRoute>
  );
}
