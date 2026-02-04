'use client';

import { useParams } from 'next/navigation';
import { AppDetail } from '@/components/apps/AppDetail';

export default function AppDetailPage() {
  const params = useParams();
  const appId = params.id as string;

  return (
    <div className="h-full overflow-y-auto">
      <AppDetail appId={appId} />
    </div>
  );
}
