'use client';

import { MarketplaceHeader } from '@/components/layout/MarketplaceHeader';
import { Footer } from '@/components/layout/Footer';
import { LoginPanel } from '@/components/auth/LoginPanel';
import { useAuth } from '@/components/auth/AuthProvider';

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isLoginPanelOpen, closeLoginPanel } = useAuth();

  return (
    <div className="min-h-screen bg-[#0B0F17] flex flex-col">
      <MarketplaceHeader />
      <main className="flex-1">
        {children}
      </main>
      <Footer />
      <LoginPanel isOpen={isLoginPanelOpen} onClose={closeLoginPanel} />
    </div>
  );
}
