'use client';

import { useEffect } from 'react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import Image from '@tschk/moonshine-next/image';
import { useAuth } from './AuthProvider';
import { loginUrlReturningTo } from '@/lib/loginNext';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      // Return here after sign-in, e.g. a conversation opened from an h.omi.me link.
      router.push(
        loginUrlReturningTo(`${window.location.pathname}${window.location.search}`),
      );
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
