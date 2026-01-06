'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useAuth } from '@/components/auth/AuthProvider';

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (user) {
        router.push('/conversations');
      } else {
        router.push('/login');
      }
    }
  }, [user, loading, router]);

  // Show loading while determining redirect
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary">
      <div className="w-16 h-16 relative">
        <Image
          src="/logo.png"
          alt="Omi"
          fill
          className="object-contain animate-pulse"
        />
      </div>
    </div>
  );
}
