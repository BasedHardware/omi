'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import {
  getPeople,
  createPerson,
  updatePersonName,
  deletePerson,
} from '@/features/conversations/api';
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

function messageFor(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function sortPeople(people: Person[]): Person[] {
  return [...people].sort((a, b) => a.name.localeCompare(b.name));
}

export function createPeopleStore() {
  const people = createSignal<Person[]>([]);
  const loading = createSignal(true);
  const error = createSignal<string | null>(null);
  const mutationTails = new Map<string, Promise<void>>();

  const enqueueMutation = <T>(id: string, mutation: () => Promise<T>): Promise<T> => {
    const previous = mutationTails.get(id);
    const result = previous ? previous.then(mutation) : mutation();
    const tail = result.then(
      () => undefined,
      () => undefined,
    );
    mutationTails.set(id, tail);
    void tail.then(() => {
      if (mutationTails.get(id) === tail) mutationTails.delete(id);
    });
    return result;
  };

  const load = async () => {
    loading.set(true);
    try {
      people.set(sortPeople(await getPeople()));
      error.set(null);
    } catch (err) {
      console.error('Failed to fetch people:', err);
      error.set('Failed to load people');
    } finally {
      loading.set(false);
    }
  };

  const add = async (name: string): Promise<Person | null> => {
    try {
      const created = await createPerson(name);
      people.set((current) => sortPeople([...current, created]));
      error.set(null);
      return created;
    } catch (err) {
      console.error('Failed to create person:', err);
      error.set(messageFor(err, 'Failed to create person'));
      return null;
    }
  };

  const update = (personId: string, name: string): Promise<boolean> =>
    enqueueMutation(personId, async () => {
      const previous = people.peek().find((person) => person.id === personId);
      if (!previous) return false;
      people.set((current) =>
        sortPeople(current.map((person) => (person.id === personId ? { ...person, name } : person))),
      );
      try {
        await updatePersonName(personId, name);
        error.set(null);
        return true;
      } catch (err) {
        console.error('Failed to update person:', err);
        people.set((current) =>
          current.map((person) => (person.id === personId ? previous : person)),
        );
        error.set(messageFor(err, 'Failed to update person'));
        return false;
      }
    });

  const remove = (personId: string): Promise<boolean> =>
    enqueueMutation(personId, async () => {
      const removed = people.peek().find((person) => person.id === personId);
      people.set((current) => current.filter((person) => person.id !== personId));
      try {
        await deletePerson(personId);
        error.set(null);
        return true;
      } catch (err) {
        console.error('Failed to delete person:', err);
        if (removed) {
          people.set((current) => sortPeople([...current, removed]));
        }
        error.set(messageFor(err, 'Failed to delete person'));
        return false;
      }
    });

  return { people, loading, error, load, add, update, remove };
}

export function usePeople(): UsePeopleReturn {
  const store = useMemo(() => createPeopleStore(), []);

  useEffect(() => {
    void store.load();
  }, [store]);

  const people = useSignalValue(store.people);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);

  const addPerson = useCallback((name: string) => store.add(name), [store]);
  const updatePerson = useCallback(
    (personId: string, name: string) => store.update(personId, name),
    [store],
  );
  const removePerson = useCallback((personId: string) => store.remove(personId), [store]);

  return {
    people,
    loading,
    error,
    refresh: store.load,
    addPerson,
    updatePerson,
    removePerson,
  };
}
