'use client';

import { useEffect } from 'react';
import { TaskHub } from '@/components/tasks/TaskHub';
import { PostHogManager } from '@/lib/analytics/posthog';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

export default function TasksPage() {
  useEffect(() => {
    PostHogManager.pageView('Tasks');
  }, []);

  return <TaskHub />;
}

registerMoonshineRoute('/tasks', TasksPage, 'authenticated');
