'use client';

import { useEffect } from 'react';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function Settings() {
  useEffect(() => {
    MixpanelManager.pageView('Settings');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <SettingsPage />
    </div>
  );
}

registerMoonshineRoute('/settings', Settings, 'authenticated');
