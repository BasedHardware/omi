'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/components/auth-provider';
import { getFirebaseDb } from '@/lib/firebase/client';
import { collection, query, where, getDocs, DocumentData } from 'firebase/firestore';
import { OmiApp } from '@/lib/services/omi-api/types';

export function usePrivateApps() {
  const { user, loading: authLoading } = useAuth();
  const [privateApps, setPrivateApps] = useState<OmiApp[]>([]);
  const [isLoadingPrivate, setIsLoadingPrivate] = useState<boolean>(true);
  const [errorPrivate, setErrorPrivate] = useState<Error | null>(null);

  useEffect(() => {
    // Only run query if auth is done and user exists
    if (!authLoading && user) {
      const fetchPrivateApps = async () => {
        setIsLoadingPrivate(true);
        setErrorPrivate(null);
        try {
          const appsCollection = collection(getFirebaseDb(), 'plugins_data');
          const q = query(
            appsCollection, 
            where('private', '==', true),
            where('deleted', '!=', true) // Assuming deleted is marked true when deleted
          );
          
          const querySnapshot = await getDocs(q);
          const appsData = querySnapshot.docs.map(doc => ({
            id: doc.id,
            ...(doc.data() as DocumentData),
            // Add any necessary type casting or transformations here if Firestore data structure differs from OmiApp
          })) as OmiApp[]; // Cast the result array
          
          setPrivateApps(appsData);

        } catch (err) {
          console.error("Error fetching private apps from Firestore:", err);
          setErrorPrivate(err instanceof Error ? err : new Error('Failed to fetch private apps'));
          setPrivateApps([]); // Clear data on error
        } finally {
          setIsLoadingPrivate(false);
        }
      };

      fetchPrivateApps();
    } else if (!authLoading && !user) {
      // If auth is done loading and there's no user, there are no private apps to fetch
      setPrivateApps([]);
      setIsLoadingPrivate(false);
      setErrorPrivate(null);
    }
    // Initial loading state while auth is resolving
    else if (authLoading) {
        setIsLoadingPrivate(true);
    }

  }, [user, authLoading]); // Rerun effect when user or auth loading state changes

  return {
    privateApps,
    isLoadingPrivate,
    errorPrivate,
  };
} 