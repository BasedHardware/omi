'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User, onAuthStateChanged, signOut as firebaseSignOut } from 'firebase/auth';
import { getFirebaseAuth } from '@/lib/firebase/client';
import { useRouter } from 'next/navigation'; // Use next/navigation for App Router

interface AuthContextProps {
  user: User | null;
  isAdmin: boolean;
  loading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextProps>({
  user: null,
  isAdmin: false,
  loading: true,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const bypassAuth = process.env.NEXT_PUBLIC_DEV_BYPASS_AUTH === '1';
  const [user, setUser] = useState<User | null>(bypassAuth ? ({ uid: 'dev-admin' } as User) : null);
  const [isAdmin, setIsAdmin] = useState<boolean>(bypassAuth);
  const [loading, setLoading] = useState<boolean>(!bypassAuth);
  const router = useRouter();

  const signOut = async () => {
    try {
      await firebaseSignOut(getFirebaseAuth());
      setUser(null);
      setIsAdmin(false);
      router.push('/login'); // Redirect to login after sign out
    } catch (error) {
      console.error('Error signing out:', error);
    }
  };

  useEffect(() => {
    if (bypassAuth) {
      setUser({ uid: 'dev-admin' } as User);
      setIsAdmin(true);
      setLoading(false);
      return;
    }

    const auth = getFirebaseAuth();
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setLoading(true);
      if (currentUser) {
        console.log('currentUser', currentUser);
        // Check admin status via server-side API (Admin SDK bypasses Firestore security rules)
        try {
          const idToken = await currentUser.getIdToken();
          const res = await fetch('/api/auth/check-admin', {
            headers: { Authorization: `Bearer ${idToken}` },
          });
          const data = await res.json();
          if (data.isAdmin) {
            setUser(currentUser);
            setIsAdmin(true);
            console.log(`Admin user ${currentUser.email} signed in.`);
          } else {
            console.warn(`User ${currentUser.email} is not an admin. Signing out.`);
            await firebaseSignOut(auth);
            setUser(null);
            setIsAdmin(false);
            router.push('/login?error=unauthorized');
          }
        } catch (error) {
          console.error('Error checking admin status:', error);
          await firebaseSignOut(auth);
          setUser(null);
          setIsAdmin(false);
          router.push('/login?error=check_failed');
        }
      } else {
        setUser(null);
        setIsAdmin(false);
      }
      setLoading(false);
    });

    // Cleanup subscription on unmount
    return () => unsubscribe();
  }, [bypassAuth, router]); // Add router to dependency array

  return (
    <AuthContext.Provider value={{ user, isAdmin, loading, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext); 
