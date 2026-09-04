import {useCallback, useEffect, useRef, useState} from 'react';
import {omiAuth, subscribeOmiBackendSessionInvalidated} from '../omiNative';

export function useOnboarding(
  macDesktop: boolean,
  refreshReads: (initial: boolean) => Promise<void>,
) {
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [onboardingRequired, setOnboardingRequired] = useState<boolean | null>(
    macDesktop ? null : false,
  );
  const authOperationRef = useRef(0);

  useEffect(() => {
    let active = true;
    const auth = omiAuth;
    if (!macDesktop) {
      setOnboardingRequired(false);
      return () => {
        active = false;
      };
    }
    if (auth === undefined || auth === null) {
      // A Mac without the native OmiAuth module can never establish a real
      // cloud session. It must stay on Welcome — never a faked ready shell.
      setOnboardingRequired(true);
      return () => {
        active = false;
      };
    }
    Promise.all([auth.hasCompletedOnboarding(), auth.hasCloudSession()])
      .then(async ([completed, hasSession]) => {
        if (hasSession && !completed) {
          await auth.markOnboardingComplete();
        }
        if (active) {
          setOnboardingRequired(!hasSession);
        }
      })
      .catch(() => {
        if (active) {
          setOnboardingRequired(true);
        }
      });
    return () => {
      active = false;
    };
  }, [macDesktop]);

  // Every sign-in path — first-run Welcome, Settings, Connectors, Home
  // recovery — is the same native OmiAuth session. A successful signIn always
  // records completion and leaves first-run, so no surface can strand the
  // user on Welcome after the native session is established.
  const signInAndRefresh = useCallback(async () => {
    if (omiAuth === undefined || omiAuth === null) {
      return;
    }
    const operation = ++authOperationRef.current;
    setAuthError(null);
    setSigningIn(true);
    try {
      const result = await omiAuth.signIn();
      if (operation !== authOperationRef.current) {
        return;
      }
      if (result.signedIn) {
        await omiAuth.markOnboardingComplete();
        if (operation !== authOperationRef.current) {
          return;
        }
        setOnboardingRequired(false);
        await refreshReads(false);
      } else {
        setAuthError('Sign in was not completed. Try again.');
      }
    } catch (error) {
      if (operation === authOperationRef.current) {
        setAuthError('Sign in was not completed. Try again.');
      }
      throw error;
    } finally {
      if (operation === authOperationRef.current) {
        setSigningIn(false);
      }
    }
  }, [refreshReads]);

  const completeFirstRun = signInAndRefresh;

  const signOutAndRefresh = useCallback(async () => {
    const auth = omiAuth;
    if (auth === undefined || auth === null) {
      throw new Error('Sign out is not available in this app session.');
    }
    const operation = ++authOperationRef.current;
    const result = await auth.signOut();
    if (!result.signedOut) {
      throw new Error('Could not clear this app session.');
    }
    // After the keychain session is gone the desktop gate must fall back to
    // Welcome even if the confirmation probe itself fails, so a cleared
    // session can never leave a signed-out Mac pinned in the product shell.
    let hasSession = false;
    try {
      hasSession = await auth.hasCloudSession();
    } catch {
      hasSession = false;
    }
    if (operation === authOperationRef.current && macDesktop && !hasSession) {
      setOnboardingRequired(true);
    }
    // No refreshReads here: a signed-out Mac must not fire cloud reads, and
    // a late response must not overwrite the next session's fresh load.
  }, [macDesktop]);

  // A ready session can die mid-run (native refresh cleared the keychain on a
  // definitive failure). Chat/read 401s and unconfigured credentials call
  // this; if the keychain session is really gone the gate falls back to the
  // same Welcome as sign-out instead of keeping signed-in chrome up.
  const revalidateSession = useCallback(async () => {
    const auth = omiAuth;
    if (!macDesktop || auth === undefined || auth === null) {
      return;
    }
    const operation = authOperationRef.current;
    let hasSession = false;
    try {
      hasSession = await auth.hasCloudSession();
    } catch {
      hasSession = false;
    }
    if (operation === authOperationRef.current && !hasSession) {
      setOnboardingRequired(true);
    }
  }, [macDesktop]);

  useEffect(() => {
    if (!macDesktop) {
      return;
    }
    return subscribeOmiBackendSessionInvalidated(() => {
      revalidateSession().catch(() => undefined);
    });
  }, [macDesktop, revalidateSession]);

  return {
    authError,
    completeFirstRun,
    onboardingRequired,
    revalidateSession,
    signInAndRefresh,
    signOutAndRefresh,
    signingIn,
  };
}
