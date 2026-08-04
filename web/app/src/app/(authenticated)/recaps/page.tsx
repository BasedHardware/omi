'use client';

import { RecapsPage } from '@/components/recaps/RecapsPage';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function RecapsRoute() {
  return <RecapsPage />;
}

registerMoonshineRoute('/recaps', RecapsRoute, 'authenticated');
