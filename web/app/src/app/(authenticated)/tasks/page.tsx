'use client';

import { useEffect } from 'react';
import { TaskHub } from '@/components/tasks/TaskHub';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function TasksPage() {
  useEffect(() => {
    MixpanelManager.pageView('Tasks');
  }, []);

  return <TaskHub />;
}

registerMoonshineRoute('/tasks', TasksPage, 'authenticated');
