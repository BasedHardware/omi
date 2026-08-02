'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { useAuth } from '@/components/auth/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { claimChannelLink } from '@/lib/api';

export default function Settings() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const { showToast } = useToast();
  const channel = searchParams.get('channel');
  const code = searchParams.get('code');

  useEffect(() => {
    if (!user || !channel || !code) return;
    let active = true;
    claimChannelLink(channel, code)
      .then(() => {
        if (!active) return;
        showToast('Channel connected', 'success');
        router.replace('/settings?section=integrations');
      })
      .catch(() => {
        if (!active) return;
        showToast('This link is invalid or expired', 'error');
      });
    return () => {
      active = false;
    };
  }, [channel, code, router, showToast, user]);

  useEffect(() => {
    MixpanelManager.pageView('Settings');
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <SettingsPage />
    </div>
  );
}
