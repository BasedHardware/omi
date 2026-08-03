'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  MISSING_CONFIG_MESSAGE,
  isFirebaseConfigured,
  onAuthStateChange,
  signInWithGoogle,
} from '@/lib/firebase';

export default function LoginPage() {
  const router = useRouter();
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState<string | null>(
    isFirebaseConfigured ? null : MISSING_CONFIG_MESSAGE,
  );

  // Already signed in? There is nothing to do on this page.
  useEffect(() => {
    if (!isFirebaseConfigured) return;
    return onAuthStateChange((user) => {
      if (user) router.replace('/today');
    });
  }, [router]);

  const handleSignIn = useCallback(async () => {
    setSigningIn(true);
    setError(null);
    try {
      await signInWithGoogle();
      router.replace('/today');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.');
      setSigningIn(false);
    }
  }, [router]);

  return (
    <main className="wrap top">
      <h1 className="masthead">PAPER</h1>
      <p className="dateline">Sign in &middot; Then it prints</p>

      <div className="signin">
        <p className="sub">
          It builds from your own record, so it needs to know whose day to read.
        </p>

        <div className="actions">
          <button
            type="button"
            className="cta"
            onClick={handleSignIn}
            disabled={signingIn || !isFirebaseConfigured}
          >
            {signingIn ? 'Signing in…' : 'Sign in with Google'}
          </button>
        </div>

        {error && <p className="fine">{error}</p>}
      </div>

      <footer>Built on Omi</footer>
    </main>
  );
}
