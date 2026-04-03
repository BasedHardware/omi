'use client';

import React, { useEffect } from 'react';
import { useAuth } from '@/components/auth-provider';
import { useRouter } from 'next/navigation';
import { DashboardSidebar } from "@/components/dashboard/sidebar";
import { DashboardHeader } from "@/components/dashboard/header";

// Simple loading component (Consider moving to a shared UI folder)
const LoadingScreen = () => (
  <div className="flex items-center justify-center min-h-screen">
    <div>Loading...</div>
  </div>
);

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isAdmin, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) {
      return; // Wait until loading is complete
    }
    if (!user || !isAdmin) {
      // Redirect non-admins or non-logged-in users to login
      router.push('/login?error=unauthorized');
    }
  }, [user, isAdmin, loading, router]);

  // Show loading screen while checking auth
  if (loading) {
    return <LoadingScreen />;
  }

  // If user is authenticated and is an admin, render the dashboard layout
  if (user && isAdmin) {
    return (
      <div className="min-h-screen flex bg-background">
        <DashboardSidebar />
        <div className="flex-1 flex flex-col min-h-screen">
          <DashboardHeader />
          <main className="flex-1 p-4 md:p-6 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>
    );
  }

  // Fallback while redirecting
  return <LoadingScreen />;
}