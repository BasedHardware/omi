'use client';

import { useEffect } from 'react';
import { ConversationSplitView } from '@/components/conversations/ConversationSplitView';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export default function ConversationsPage() {
  useEffect(() => {
    MixpanelManager.pageView('Conversations');
  }, []);

  return <ConversationSplitView />;
}
