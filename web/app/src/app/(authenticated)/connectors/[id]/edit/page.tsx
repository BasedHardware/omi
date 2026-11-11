'use client';

import { useState, useEffect } from 'react';
import { useParams } from '@tschk/moonshine-next/navigation';
import Link from '@tschk/moonshine-next/link';
import { AppForm } from '@/components/apps/AppForm';
import { getApp } from '@/lib/api';
import type { App } from '@/types/apps';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function EditAppPage() {
  const params = useParams();
  const appId = params.id as string;
  const [app, setApp] = useState<App | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadApp() {
      if (!appId) return;

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
      <div className="h-full flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent-primary border-t-transparent" />
      </div>
    );
  }

  if (error || !app) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'App not found'}</p>
          <Link href="/connectors" className="text-accent-primary hover:underline">
            Back to Apps
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <AppForm mode="edit" app={app} />
    </div>
  );
}

registerMoonshineRoute('/connectors/:id/edit', EditAppPage, 'authenticated');
