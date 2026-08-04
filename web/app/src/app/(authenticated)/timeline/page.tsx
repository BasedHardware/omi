'use client';

import { useEffect } from 'react';
import { TimelineSplitView } from '@/components/timeline/TimelineSplitView';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function TimelinePage() {
  useEffect(() => {
    MixpanelManager.pageView('Timeline');
  }, []);

  return <TimelineSplitView />;
}

registerMoonshineRoute('/timeline', TimelinePage, 'authenticated');
