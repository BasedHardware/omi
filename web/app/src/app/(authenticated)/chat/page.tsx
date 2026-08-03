'use client';

import { useEffect } from 'react';
import { FullPageChat } from '@/components/chat/FullPageChat';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function ChatPage() {
  useEffect(() => {
    MixpanelManager.pageView('Chat');
  }, []);

  return <FullPageChat />;
}

registerMoonshineRoute('/chat', ChatPage, 'authenticated');
