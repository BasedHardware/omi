'use client';

import { useEffect } from 'react';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function Settings() {
  useEffect(() => {
    PostHogManager.pageView('Settings');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <SettingsPage />
    </div>
  );
}

registerMoonshineRoute('/settings', Settings, 'authenticated');
