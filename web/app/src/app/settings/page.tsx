'use client';

import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { SettingsPage } from '@/components/settings/SettingsPage';

function SettingsContent() {
  return (
    <MainLayout hideHeader>
      <div className="h-full overflow-y-auto">
        <SettingsPage />
      </div>
    </MainLayout>
  );
}

export default function Settings() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}
