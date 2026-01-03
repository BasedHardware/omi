'use client';

import { AppForm } from '@/components/apps/AppForm';

export default function NewAppPage() {
  return (
    <div className="h-full overflow-y-auto">
      <AppForm mode="create" />
    </div>
  );
}
