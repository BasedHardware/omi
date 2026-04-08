'use client';

import React, { useEffect } from 'react';
import { GoogleAuthProvider, signInWithPopup } from 'firebase/auth';
import { getFirebaseAuth } from '@/lib/firebase/client';
import { useAuth } from '@/components/auth-provider';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Chrome } from 'lucide-react'; // Using Chrome icon for Google

// Simple spinner placeholder
const Spinner = () => (
  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
);

const LoadingScreen = ({ message }: { message: string }) => (
  <div className="flex flex-col items-center justify-center min-h-screen space-y-4">
    <Spinner />
    <p>{message}</p>
  </div>
);


export default function LoginPage() {
  const { user, isAdmin, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const error = searchParams?.get('error');

  const handleSignIn = async () => {
    const provider = new GoogleAuthProvider();
    try {
      await signInWithPopup(getFirebaseAuth(), provider);
      // AuthProvider will handle redirection and admin check
    } catch (error) {
      console.error('Error signing in with Google:', error);
      // You could potentially show error messages here too
    }
  };

  useEffect(() => {
    // If user is loaded, authenticated, and admin, redirect to home
    if (!loading && user && isAdmin) {
      router.push('/');
    }
  }, [user, isAdmin, loading, router]);

  // Show loading state
  if (loading) {
    return <LoadingScreen message="Loading session..." />;
  }

  // If user is logged in but redirect hasn't happened yet (or failed admin check),
  // show a checking authorization state.
  if (user && !isAdmin) {
    return <LoadingScreen message="Checking authorization..." />;
  }

  // If not logged in, show the login card
  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <Card className="w-full max-w-sm mx-4">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Admin Login</CardTitle>
            <CardDescription>Sign in using your authorized Google account.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {error === 'unauthorized' && (
                <p className="text-sm text-center text-destructive">
                  Access denied. Your account is not authorized.
                </p>
              )}
              {error === 'check_failed' && (
                <p className="text-sm text-center text-destructive">
                  Authorization check failed. Please try again.
                </p>
              )}
              <Button onClick={handleSignIn} className="w-full">
                 <Chrome className="mr-2 h-4 w-4" /> Sign in with Google
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Fallback shouldn't normally be reached if logic above is correct
  return <LoadingScreen message="Redirecting..." />;
} 