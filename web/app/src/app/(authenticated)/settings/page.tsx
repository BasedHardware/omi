'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from '@tschk/moonshine-next/navigation';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { useAuth } from '@/components/auth/AuthProvider';
import { useToast } from '@/components/ui/Toast';
import { claimChannelLink } from '@/lib/api';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

/**
 * What to tell someone whose channel link did not go through.
 *
 * "Invalid or expired" is only true for a rejected code. An already-linked
 * channel, an expired session and a dropped connection each have a different
 * thing for the reader to do, and collapsing them into one message hides it.
 *
 * `lib/api` currently throws plain `Error`s carrying the status in their
 * message, so this reads the message; the durable fix is a typed `ApiError`
 * with `status` on it.
 */
export function describeChannelLinkError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);

  if (/network error|failed to fetch/i.test(message)) {
    return 'Could not reach Omi. Check your connection and try the link again.';
  }
  if (/unauthorized|not authenticated|\b401\b/i.test(message)) {
    return 'Your session expired. Sign in again, then reopen the link.';
  }
  if (/\b409\b/.test(message)) {
    return 'That channel is already linked to an account.';
  }
  if (/\b400\b/.test(message)) {
    return 'This link is invalid or expired';
  }
  return 'Could not connect the channel. Try the link again.';
}

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
        router.replace('/connectors?tab=services');
      })
      .catch((error: unknown) => {
        if (!active) return;
        showToast(describeChannelLinkError(error), 'error');
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

registerMoonshineRoute('/settings', Settings, 'authenticated');
