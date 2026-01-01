'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { AppForm } from '@/components/apps/AppForm';
import { getApp } from '@/lib/api';
import type { App } from '@/types/apps';

function EditAppContent() {
  const params = useParams();
  const appId = params.id as string;
  const [app, setApp] = useState<App | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadApp() {
      try {
        const appData = await getApp(appId);
        setApp(appData);
      } catch (err) {
        console.error('Failed to load app:', err);
        setError('Failed to load app');
      } finally {
        setIsLoading(false);
      }
    }
    loadApp();
  }, [appId]);

  if (isLoading) {
    return (
      <MainLayout hideHeader>
        <div className="h-full flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent-primary border-t-transparent" />
        </div>
      </MainLayout>
    );
  }

  if (error || !app) {
    return (
      <MainLayout hideHeader>
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <p className="text-red-400 mb-4">{error || 'App not found'}</p>
            <a href="/apps" className="text-accent-primary hover:underline">
              Back to Apps
            </a>
          </div>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout hideHeader>
      <div className="h-full overflow-y-auto">
        <AppForm mode="edit" app={app} />
      </div>
    </MainLayout>
  );
}

export default function EditAppPage() {
  return (
    <ProtectedRoute>
      <EditAppContent />
    </ProtectedRoute>
  );
}
