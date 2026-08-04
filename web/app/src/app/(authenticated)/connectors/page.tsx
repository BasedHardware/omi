'use client';

import { useEffect } from 'react';
import { AppsExplorer } from '@/components/apps/AppsExplorer';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function AppsPage() {
  useEffect(() => {
    MixpanelManager.pageView('Apps');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <AppsExplorer />
    </div>
  );
}

registerMoonshineRoute('/my-apps', AppsPage, 'authenticated');
