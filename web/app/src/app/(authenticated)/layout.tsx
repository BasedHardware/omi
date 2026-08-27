import { ProtectedRoute } from '@/features/auth';
import { MainLayout } from '@/components/layout/MainLayout';
import { StartupModals } from '@/shared/ui/StartupModals';

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <MainLayout hideHeader>{children}</MainLayout>
      <StartupModals />
    </ProtectedRoute>
  );
}
