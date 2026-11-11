'use client';

import { useEffect } from 'react';
import { DevelopersPage } from '@/components/developers/DevelopersPage';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function Developers() {
  useEffect(() => {
    PostHogManager.pageView('Developers');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <DevelopersPage />
    </div>
  );
}

registerMoonshineRoute('/developers', Developers, 'authenticated');
