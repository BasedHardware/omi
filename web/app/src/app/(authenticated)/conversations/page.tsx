'use client';

import { useEffect } from 'react';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function ConversationsPage() {
  useEffect(() => {
    MixpanelManager.pageView('Conversations');
  }, []);

  return <ConversationSplitView />;
}

registerMoonshineRoute('/conversations', ConversationsPage, 'authenticated');
