'use client';

import { useCallback, useSyncExternalStore } from 'react';
import type { Resource, Signal } from '@tschk/moonshine';

/**
 * React bridges for moonshine signals.
 *
 * Deliberately hand-written rather than imported from `@tschk/moonshine-react`.
 * That package's entry point also pulls in its SSR renderer and island
 * hydration, which call `import(specifier)` with a runtime variable; neither
 * webpack nor Turbopack can resolve those, so importing it fails the Next
 * build with module-not-found. Its `exports` map exposes only `.`, so the
 * usable half cannot be deep-imported either.
 *
 * All we need from moonshine here is the signal kernel plus these two
 * `useSyncExternalStore` adapters, which are the same shape as the upstream
 * ones.
 */

/** Subscribe a component to a signal's current value. */
export function useSignalValue<T>(signal: Signal<T>): T {
  // A fresh `subscribe` identity makes useSyncExternalStore resubscribe every
  // render, so keep it stable for as long as the signal is.
  const subscribe = useCallback(
    (onChange: () => void) => signal.subscribe(onChange),
    [signal],
  );
  const read = useCallback(() => signal.peek(), [signal]);
  return useSyncExternalStore(subscribe, read, read);
}

export interface ResourceSnapshot<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
  refetch: () => Promise<T | undefined>;
}

/** Subscribe a component to a resource's value, loading, and error signals. */
export function useResourceValue<T>(resource: Resource<T>): ResourceSnapshot<T> {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const offs = [
        resource.subscribe(onChange),
        resource.loading.subscribe(onChange),
        resource.error.subscribe(onChange),
      ];
      return () => offs.forEach((off) => off());
    },
    [resource],
  );

  // The three signals move together, so one version counter is enough to tell
  // React something changed; the values themselves are read below.
  const version = useCallback(
    () =>
      `${resource.status.peek()}:${String(resource.loading.peek())}:${
        resource.error.peek()?.message ?? ''
      }:${resource.peek() === undefined ? 'empty' : 'set'}`,
    [resource],
  );

  useSyncExternalStore(subscribe, version, version);

  return {
    data: resource.peek(),
    loading: resource.loading.peek(),
    error: resource.error.peek(),
    refetch: resource.refetch,
  };
}
