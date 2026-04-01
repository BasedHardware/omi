'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/components/auth-provider';
import { db } from '@/lib/firebase/client';
import { collection, getDocs, DocumentData } from 'firebase/firestore';

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  email: string;
  createdAt?: any;
}

export function useTeamMembers() {
  const { user, loading: authLoading } = useAuth();
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // Only run query if auth is done and user exists
    if (!authLoading && user) {
      const fetchTeamMembers = async () => {
        setIsLoading(true);
        setError(null);
        try {
          // Fetch from adminData collection
          const usersCollection = collection(db, 'adminData');
          const querySnapshot = await getDocs(usersCollection);
          
          const members = querySnapshot.docs.map(doc => {
            const data = doc.data() as DocumentData;
            return {
              id: doc.id,
              name: data.name || 'Unknown',
              role: data.role || 'Admin',
              email: data.email || 'No email',
              createdAt: data.createdAt,
            };
          });
          
          setTeamMembers(members);

        } catch (err) {
          console.error("Error fetching team members from Firestore:", err);
          setError(err instanceof Error ? err : new Error('Failed to fetch team members'));
          setTeamMembers([]); // Clear data on error
        } finally {
          setIsLoading(false);
        }
      };

      fetchTeamMembers();
    } else if (!authLoading && !user) {
      // If auth is done loading and there's no user, there are no team members to fetch
      setTeamMembers([]);
      setIsLoading(false);
      setError(null);
    }
    // Initial loading state while auth is resolving
    else if (authLoading) {
        setIsLoading(true);
    }

  }, [user, authLoading]); // Rerun effect when user or auth loading state changes

  return {
    teamMembers,
    isLoading,
    error,
  };
}
