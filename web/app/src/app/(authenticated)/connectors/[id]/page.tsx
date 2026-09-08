'use client';

import { useParams } from '@tschk/moonshine-next/navigation';
import { AppDetail } from '@/components/apps/AppDetail';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function AppDetailPage() {
  const params = useParams();
  const appId = params.id as string;

  return (
    <div className="h-full overflow-y-auto">
      <AppDetail appId={appId} />
    </div>
  );
}

registerMoonshineRoute('/connectors/:id', AppDetailPage, 'authenticated');
