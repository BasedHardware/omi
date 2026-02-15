'use client';

import { useState, useEffect, useCallback } from 'react';
import { getPeople, createPerson, updatePersonName, deletePerson } from '@/lib/api';
import type { Person } from '@/types/user';

interface UsePeopleReturn {
  people: Person[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addPerson: (name: string) => Promise<Person | null>;
  updatePerson: (personId: string, name: string) => Promise<boolean>;
  removePerson: (personId: string) => Promise<boolean>;
}

/**
 * Hook to manage people (speakers) for transcript identification
 */
export function usePeople(): UsePeopleReturn {
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPeople = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPeople();
      // Sort alphabetically by name
      setPeople(data.sort((a, b) => a.name.localeCompare(b.name)));
    } catch (err) {
      console.error('Failed to fetch people:', err);
      setError('Failed to load people');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPeople();
  }, [fetchPeople]);

  const addPerson = useCallback(async (name: string): Promise<Person | null> => {
    try {
      const newPerson = await createPerson(name);
      setPeople(prev => [...prev, newPerson].sort((a, b) => a.name.localeCompare(b.name)));
      return newPerson;
    } catch (err) {
      console.error('Failed to create person:', err);
      return null;
    }
  }, []);

  const updatePerson = useCallback(async (personId: string, name: string): Promise<boolean> => {
    try {
      await updatePersonName(personId, name);
      setPeople(prev =>
        prev
          .map(p => (p.id === personId ? { ...p, name } : p))
          .sort((a, b) => a.name.localeCompare(b.name))
      );
      return true;
    } catch (err) {
      console.error('Failed to update person:', err);
      return false;
    }
  }, []);

  const removePerson = useCallback(async (personId: string): Promise<boolean> => {
    try {
      await deletePerson(personId);
      setPeople(prev => prev.filter(p => p.id !== personId));
      return true;
    } catch (err) {
      console.error('Failed to delete person:', err);
      return false;
    }
  }, []);

  return {
    people,
    loading,
    error,
    refresh: fetchPeople,
    addPerson,
    updatePerson,
    removePerson,
  };
}
