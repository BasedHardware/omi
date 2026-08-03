'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  MISSING_CONFIG_MESSAGE,
  getIdToken,
  isFirebaseConfigured,
  onAuthStateChange,
  signOutUser,
} from '@/lib/firebase';
import { localToday, type Edition } from '@/lib/edition';
import { EditionView } from './EditionView';

type State =
  | { status: 'loading' }
  | { status: 'ready'; edition: Edition }
  | { status: 'error'; message: string };

/** FastAPI errors arrive as `{"detail": ...}`; anything else is shown as it came. */
function describeFailure(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body);
    const detail = parsed?.detail ?? parsed?.error;
    if (typeof detail === 'string' && detail) return `${status} — ${detail}`;
  } catch {
    // Not JSON. Fall through and print what the backend actually sent.
  }
  const text = body.trim().slice(0, 300);
  return text ? `${status} — ${text}` : `${status} — the backend returned no detail.`;
}

export default function TodayPage() {
  const router = useRouter();
  const [state, setState] = useState<State>(
    isFirebaseConfigured
      ? { status: 'loading' }
      : { status: 'error', message: MISSING_CONFIG_MESSAGE },
  );

  const fetchEdition = useCallback(async () => {
    setState({ status: 'loading' });
    const date = localToday();

    let token: string | null;
    try {
      token = await getIdToken();
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Could not read your session.',
      });
      return;
    }
    if (!token) {
      router.replace('/login');
      return;
    }

    try {
      const response = await fetch(`/api/proxy/v1/paper/${date}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        setState({
          status: 'error',
          message: describeFailure(response.status, await response.text()),
        });
        return;
      }
      setState({ status: 'ready', edition: (await response.json()) as Edition });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : 'The request failed.',
      });
    }
  }, [router]);

  useEffect(() => {
    if (!isFirebaseConfigured) return;
    return onAuthStateChange((user) => {
      if (!user) {
        router.replace('/login');
        return;
      }
      void fetchEdition();
    });
  }, [router, fetchEdition]);

  const handleSignOut = useCallback(async () => {
    await signOutUser();
    router.replace('/login');
  }, [router]);

  return (
    <main className="wrap top edition">
      <h1 className="masthead">PAPER</h1>

      {state.status === 'loading' && (
        <>
          <p className="dateline">Setting today&rsquo;s edition</p>
          <p className="quiet">Reading your day&hellip;</p>
        </>
      )}

      {/* A failure prints the reason. It never prints a paper we did not receive. */}
      {state.status === 'error' && (
        <>
          <p className="dateline">Nothing printed</p>
          <p className="quiet">
            Today&rsquo;s edition could not be built.
            <span className="stamp">{state.message}</span>
          </p>
          <div className="actions">
            <button type="button" className="cta" onClick={() => void fetchEdition()}>
              Try again
            </button>
          </div>
        </>
      )}

      {state.status === 'ready' && <EditionView edition={state.edition} />}

      {state.status === 'ready' && (
        <footer>
          <button
            type="button"
            className="cta-secondary"
            onClick={() => void handleSignOut()}
          >
            Sign out
          </button>
        </footer>
      )}
    </main>
  );
}
