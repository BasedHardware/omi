'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { AppsExplorer } from '@/components/apps/AppsExplorer';

function AppsContent() {
  return (
    <MainLayout>
      <AppsExplorer />
    </MainLayout>
  );
}

export default function AppsPage() {
  return (
    <ProtectedRoute>
      <AppsContent />
    </ProtectedRoute>
  );
}
