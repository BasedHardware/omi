'use client';

import { useEffect } from 'react';
import { ItemListPage } from '@/components/items/ItemListPage';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function ItemsRoute() {
  useEffect(() => {
    PostHogManager.pageView('Items');
  }, []);

  return <ItemListPage />;
}

registerMoonshineRoute('/items', ItemsRoute, 'authenticated');
