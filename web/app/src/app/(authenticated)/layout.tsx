import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { StartupModals } from '@/components/ui/StartupModals';

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <MainLayout hideHeader>{children}</MainLayout>
      <StartupModals />
    </ProtectedRoute>
  );
}
