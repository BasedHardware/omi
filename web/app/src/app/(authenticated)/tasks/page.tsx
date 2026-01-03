'use client';

import { useEffect } from 'react';
import { TaskHub } from '@/components/tasks/TaskHub';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export default function TasksPage() {
  useEffect(() => {
    MixpanelManager.pageView('Tasks');
  }, []);

  return <TaskHub />;
}
