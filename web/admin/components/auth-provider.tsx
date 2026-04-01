'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User, onAuthStateChanged, signOut as firebaseSignOut } from 'firebase/auth';
import { doc, getDoc } from 'firebase/firestore';
import { auth, db } from '@/lib/firebase/client';
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
      await firebaseSignOut(auth);
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

    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setLoading(true);
      if (currentUser) {
        console.log('currentUser', currentUser);
        // Check if user is an Omi admin by looking for their UID in the specific product path
        const adminDocRef = doc(db, 'adminData', currentUser.uid);
        try {
          const adminDoc = await getDoc(adminDocRef);
          if (adminDoc.exists()) {
            setUser(currentUser);
            setIsAdmin(true);
            console.log(`Admin user ${currentUser.email} signed in.`);
            // Optional: Redirect admin to a specific page upon successful login
            // if (window.location.pathname === '/login') {
            //   router.push('/');
            // }
          } else {
            console.warn(`User ${currentUser.email} is not an admin. Signing out.`);
            await firebaseSignOut(auth);
            setUser(null);
            setIsAdmin(false);
            router.push('/login?error=unauthorized'); // Redirect non-admin to login
          }
        } catch (error) {
          console.error('Error checking admin status:', error);
          await firebaseSignOut(auth);
          setUser(null);
          setIsAdmin(false);
          router.push('/login?error=check_failed'); // Redirect on error
        }
      } else {
        setUser(null);
        setIsAdmin(false);
        // Optional: Redirect non-logged-in users trying to access protected routes
        // Consider adding logic here or in specific page components/middleware
        // Example: if (!['/login'].includes(window.location.pathname)) { router.push('/login'); }
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
