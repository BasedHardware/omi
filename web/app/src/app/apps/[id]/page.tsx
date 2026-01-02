'use client';

import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { AppDetail } from '@/components/apps/AppDetail';

function AppDetailContent() {
  const params = useParams();
  const appId = params.id as string;

  return (
    <MainLayout hideHeader>
      <div className="h-full overflow-y-auto">
        <AppDetail appId={appId} />
      </div>
    </MainLayout>
  );
}

export default function AppDetailPage() {
  return (
    <ProtectedRoute>
      <AppDetailContent />
    </ProtectedRoute>
  );
}
