'use client';

import { useEffect } from 'react';
import { HomePage } from '@/components/home/HomePage';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export default function Home() {
  useEffect(() => {
    MixpanelManager.pageView('Home');
  }, []);

  return <HomePage />;
}
