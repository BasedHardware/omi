'use client';

import { useEffect } from 'react';
import { CalendarDays } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { RecapSplitView } from './RecapSplitView';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export function RecapsPage() {
  useEffect(() => {
    MixpanelManager.pageView('Recaps');
  }, []);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Page header */}
      <PageHeader
        title="Recaps"
        icon={CalendarDays}
      />

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        <RecapSplitView />
      </div>
    </div>
  );
}
