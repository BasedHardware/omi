'use client';

import { useEffect } from 'react';
import { FairUseStatus } from '@/components/fair-use/FairUseStatus';
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
