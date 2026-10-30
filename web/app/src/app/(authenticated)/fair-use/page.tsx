'use client';

import { useEffect } from 'react';
import { FairUseStatus } from '@/components/fair-use/FairUseStatus';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function FairUsePage() {
  useEffect(() => {
    PostHogManager.pageView('Fair Use');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <FairUseStatus />
    </div>
  );
}

registerMoonshineRoute('/fair-use', FairUsePage, 'authenticated');
