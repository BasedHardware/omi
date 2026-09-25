'use client';

import { useEffect } from 'react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import Image from '@tschk/moonshine-next/image';
import { useAuth } from './AuthProvider';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  // Show loading state while checking auth
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary">
        <div className="relative h-16 w-16">
          <Image
            src="/logo.png"
            alt="Omi"
            fill
            sizes="64px"
            priority
            className="animate-pulse object-contain"
          />
        </div>
      </div>
    );
  }

  // Don't render children if not authenticated (will redirect)
  if (!user) {
    return null;
  }

  return <>{children}</>;
}
