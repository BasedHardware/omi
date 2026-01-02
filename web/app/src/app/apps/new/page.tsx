'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { AppForm } from '@/components/apps/AppForm';

function NewAppContent() {
  return (
    <MainLayout hideHeader>
      <div className="h-full overflow-y-auto">
        <AppForm mode="create" />
      </div>
    </MainLayout>
  );
}

export default function NewAppPage() {
  return (
    <ProtectedRoute>
      <NewAppContent />
    </ProtectedRoute>
  );
}
