import AppHeader from '@/src/components/shared/app-header';
import { ReactNode } from 'react';

export default function MemoriesLayout({ children }: { children: ReactNode }) {
  return (
    <div>
      <AppHeader />
      {children}
    </div>
  );
}
