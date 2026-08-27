'use client';

import { useEffect } from 'react';
import { HomePage } from '@/features/home';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function Home() {
  useEffect(() => {
    MixpanelManager.pageView('Home');
  }, []);

  return <HomePage />;
}

registerMoonshineRoute('/home', Home, 'authenticated');
