'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth-provider';

// Loading component with spinner
const LoadingScreen = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        <div className="w-8 h-8 border-4 border-gray-200 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
      <div className="text-sm text-gray-600 dark:text-gray-400">Loading...</div>
    </div>
  </div>
);

// This page acts as a protected root and redirects to the main dashboard
export default function ProtectedRootPage() {
  const router = useRouter();
  const { user, isAdmin, loading } = useAuth();

  useEffect(() => {
    // Wait for auth loading to complete
    if (loading) {
      return;
    }

    // Double-check if user is admin (AuthProvider should handle primary redirect)
    // If they are admin, redirect to the actual dashboard path.
    if (user && isAdmin) {
      router.replace('/dashboard');
    } else {
      // If somehow reached here without being an authenticated admin,
      // redirect to login (AuthProvider should usually catch this earlier).
      router.replace('/login?error=unauthorized');
    }
  }, [user, isAdmin, loading, router]);

  // Show loading indicator while redirecting
  return <LoadingScreen />;
} 