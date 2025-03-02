'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { auth, db } from '@/lib/firebase';
import { doc, getDoc } from 'firebase/firestore';
import { signOut } from 'firebase/auth';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { useSubscription } from '@/lib/subscription-context';
import Link from 'next/link';
import { formatPrice } from '@/lib/stripe';
import { toast } from 'sonner';

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const { isSubscribed, currentPlan, subscriptionEndsAt, isLoading } = useSubscription();

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged(async (authUser) => {
      if (authUser) {
        try {
          const userDoc = await getDoc(doc(db, 'users', authUser.uid));
          if (userDoc.exists()) {
            setUser({
              ...authUser,
              ...userDoc.data(),
            });
          } else {
            setUser(authUser);
          }
        } catch (error) {
          console.error('Error fetching user data:', error);
          setUser(authUser);
        }
      } else {
        router.push('/');
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, [router]);

  const handleSignOut = async () => {
    try {
      // First sign out from Firebase Auth (client-side)
      await signOut(auth);
      
      // Then call our API to clear the session cookie (server-side)
      await fetch('/api/auth/sign-out', {
        method: 'POST',
      });
      
      router.push('/');
    } catch (error) {
      console.error('Error signing out:', error);
    }
  };

  const handleManageSubscription = async () => {
    try {
      const response = await fetch('/api/create-portal-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to create portal session');
      }

      const { url } = await response.json();
      window.location.href = url;
    } catch (error) {
      console.error('Error accessing customer portal:', error);
      toast.error('Failed to access customer portal');
    }
  };

  const formatDate = (timestamp: number) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  if (loading || isLoading) {
    return (
      <div className="min-h-screen bg-black text-white">
        <Header />
        <div className="flex flex-col items-center justify-center min-h-[60vh]">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
          <p className="mt-4">Loading...</p>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <Header />
      <div className="max-w-3xl mx-auto px-4 py-12">
        <h1 className="text-3xl font-bold mb-8">Account Settings</h1>
        
        <div className="bg-zinc-900 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Profile Information</h2>
          {user && (
            <div className="space-y-4">
              <div>
                <p className="text-lg font-medium">{user.displayName || 'User'}</p>
                <p className="text-zinc-400">{user.email}</p>
              </div>
            </div>
          )}
        </div>
        
        <div className="bg-zinc-900 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Subscription</h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <p className="font-medium">Current Plan</p>
                <p className="text-zinc-400">{currentPlan === 'pro' ? 'Pro Plan' : 'Free Plan'}</p>
              </div>
              {isSubscribed && (
                <button
                  onClick={handleManageSubscription}
                  className="bg-white text-black px-4 py-2 rounded-full text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  Manage Subscription
                </button>
              )}
              {!isSubscribed && (
                <Link
                  href="/pricing"
                  className="bg-white text-black px-4 py-2 rounded-full text-sm font-medium hover:bg-gray-200 transition-colors"
                >
                  Upgrade to Pro
                </Link>
              )}
            </div>
            {isSubscribed && subscriptionEndsAt && (
              <p className="text-sm text-zinc-400">
                Next billing date: {new Date(subscriptionEndsAt).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>
        
        <div className="mt-8">
          <button
            onClick={handleSignOut}
            className="text-red-500 hover:text-red-400 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>
      <Footer />
    </div>
  );
}