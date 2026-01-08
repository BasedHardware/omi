import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import { BetaWelcomeModal } from '@/components/ui/BetaWelcomeModal';

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedRoute>
      <MainLayout hideHeader>{children}</MainLayout>
      <BetaWelcomeModal />
    </ProtectedRoute>
  );
}
