'use client';

import { useEffect } from 'react';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function ConversationsPage() {
  useEffect(() => {
    PostHogManager.pageView('Conversations');
  }, []);

  return <ConversationSplitView />;
}

registerMoonshineRoute('/conversations', ConversationsPage, 'authenticated');
