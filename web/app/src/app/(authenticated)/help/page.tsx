'use client';

import { useEffect } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { crispEmbedUrl } from '@/lib/support';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function HelpPage() {
  const { user } = useAuth();

  useEffect(() => {
    MixpanelManager.pageView('Help');
  }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-stroke px-6 py-4">
        <h1 className="text-2xl font-bold text-text-primary">Help</h1>
        <p className="mt-1 text-sm text-text-quaternary">
          Chat with the team. Replies come back here and by email.
        </p>
      </header>

      <iframe
        src={crispEmbedUrl({ email: user?.email, name: user?.displayName })}
        title="Omi support chat"
        className="min-h-0 flex-1 border-0"
      />
    </div>
  );
}

registerMoonshineRoute('/help', HelpPage, 'authenticated');
