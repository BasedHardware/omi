'use client';

import { useEffect } from 'react';
import { MemoriesPage } from '@/components/memories/MemoriesPage';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function MemoriesRoute() {
  useEffect(() => {
    PostHogManager.pageView('Memories');
  }, []);

  return <MemoriesPage />;
}

registerMoonshineRoute('/memories', MemoriesRoute, 'authenticated');
