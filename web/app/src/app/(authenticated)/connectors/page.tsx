'use client';

import { useEffect } from 'react';
import { AppsExplorer } from '@/components/apps/AppsExplorer';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function AppsPage() {
  useEffect(() => {
    PostHogManager.pageView('Connectors');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <AppsExplorer />
    </div>
  );
}

registerMoonshineRoute('/connectors', AppsPage, 'authenticated');
