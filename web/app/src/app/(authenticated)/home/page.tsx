'use client';

import { useEffect } from 'react';
import { HomePage } from '@/components/home/HomePage';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function Home() {
  useEffect(() => {
    PostHogManager.pageView('Home');
  }, []);

  return <HomePage />;
}

registerMoonshineRoute('/home', Home, 'authenticated');
