'use client';

import { useEffect } from 'react';
import { FairUseStatus } from '@/features/fair-use';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function FairUsePage() {
  useEffect(() => {
    MixpanelManager.pageView('Fair Use');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <FairUseStatus />
    </div>
  );
}

registerMoonshineRoute('/fair-use', FairUsePage, 'authenticated');
