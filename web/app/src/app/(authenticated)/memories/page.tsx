'use client';

import { useEffect } from 'react';
import { MemoriesPage } from '@/components/memories/MemoriesPage';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export default function MemoriesRoute() {
  useEffect(() => {
    MixpanelManager.pageView('Memories');
  }, []);

  return <MemoriesPage />;
}
