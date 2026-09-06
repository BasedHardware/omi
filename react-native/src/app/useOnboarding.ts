import {useCallback, useEffect, useRef, useState} from 'react';
import {omiAuth, subscribeOmiBackendSessionInvalidated} from '../omiNative';

export function useOnboarding(
  nativeSessionRequired: boolean,
  refreshReads: (
    initial: boolean,
    options?: {ignoreEnabled?: boolean},
  ) => Promise<void>,
) {
  const [setupRequired, setSetupRequired] = useState(false);
  const [completingSetup, setCompletingSetup] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [onboardingRequired, setOnboardingRequired] = useState<boolean | null>(
    null,
  );
  const authOperationRef = useRef(0);

  useEffect(
    () => () => {
      ++authOperationRef.current;
    },
    [],
  );

  useEffect(() => {
    let active = true;
    const operation = authOperationRef.current;
    const auth = omiAuth;
    if (auth === undefined || auth === null) {
      // A Mac without the native OmiAuth module can never establish a real
      // cloud session. It must stay on Welcome — never a faked ready shell.
      setOnboardingRequired(true);
      return () => {
        active = false;
      };
    }
    Promise.all([
      auth.hasCompletedOnboarding(),
      nativeSessionRequired ? auth.hasCloudSession() : Promise.resolve(true),
    ])
      .then(([completed, hasSession]) => {
        if (!active || operation !== authOperationRef.current) {
          return;
        }
        setSetupRequired(hasSession && !completed);
        setOnboardingRequired(!hasSession || !completed);
      })
      .catch(() => {
        if (active && operation === authOperationRef.current) {
          setSetupRequired(!nativeSessionRequired);
          setOnboardingRequired(true);
        }
      });
    return () => {
      active = false;
    };
  }, [nativeSessionRequired]);

  // Every sign-in path — first-run Welcome, Settings, Connectors, Home
  // recovery — is the same native OmiAuth session. Successful sign-in resumes
  // unfinished setup; only explicit setup completion enables the product.
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
        const completed = await omiAuth.hasCompletedOnboarding();
        if (operation !== authOperationRef.current) {
          return;
        }
        setSetupRequired(!completed);
        setOnboardingRequired(!completed);
        if (completed) {
          await refreshReads(false, {ignoreEnabled: true});
        }
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

  const completeSetup = useCallback(async () => {
    if (!setupRequired || completingSetup || omiAuth == null) {
      return false;
    }
    const operation = ++authOperationRef.current;
    setCompletingSetup(true);
    setAuthError(null);
    try {
      if (nativeSessionRequired && !(await omiAuth.hasCloudSession())) {
        if (operation === authOperationRef.current) {
          setSetupRequired(false);
          setOnboardingRequired(true);
        }
        return false;
      }
      if (operation !== authOperationRef.current) {
        return false;
      }
      await omiAuth.markOnboardingComplete();
      if (operation !== authOperationRef.current) {
        return false;
      }
      setSetupRequired(false);
      setOnboardingRequired(false);
      await refreshReads(false, {ignoreEnabled: true});
      return operation === authOperationRef.current;
    } catch {
      if (operation === authOperationRef.current) {
        setAuthError('Setup could not be saved. Try again.');
      }
      return false;
    } finally {
      if (operation === authOperationRef.current) {
        setCompletingSetup(false);
      }
    }
  }, [completingSetup, nativeSessionRequired, refreshReads, setupRequired]);

  const completeFirstRun = signInAndRefresh;

  const cancelSignIn = useCallback(async () => {
    ++authOperationRef.current;
    setSigningIn(false);
    setAuthError(null);
    await omiAuth?.cancelSignIn();
  }, []);

  const signOutAndRefresh = useCallback(async () => {
    const auth = omiAuth;
    if (auth === undefined || auth === null) {
      throw new Error('Sign out is not available in this app session.');
    }
    const operation = ++authOperationRef.current;
    setSigningIn(false);
    setCompletingSetup(false);
    setAuthError(null);
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
    if (
      operation === authOperationRef.current &&
      nativeSessionRequired &&
      !hasSession
    ) {
      setSetupRequired(false);
      setOnboardingRequired(true);
    }
    // No refreshReads here: a signed-out Mac must not fire cloud reads, and
    // a late response must not overwrite the next session's fresh load.
  }, [nativeSessionRequired]);

  // A ready session can die mid-run (native refresh cleared the keychain on a
  // definitive failure). Chat/read 401s and unconfigured credentials call
  // this; if the keychain session is really gone the gate falls back to the
  // same Welcome as sign-out instead of keeping signed-in chrome up.
  const revalidateSession = useCallback(async () => {
    const auth = omiAuth;
    if (!nativeSessionRequired || auth === undefined || auth === null) {
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
      ++authOperationRef.current;
      setCompletingSetup(false);
      setSigningIn(false);
      setSetupRequired(false);
      setOnboardingRequired(true);
    }
  }, [nativeSessionRequired]);

  useEffect(() => {
    if (!nativeSessionRequired) {
      return;
    }
    return subscribeOmiBackendSessionInvalidated(() => {
      revalidateSession().catch(() => undefined);
    });
  }, [nativeSessionRequired, revalidateSession]);

  return {
    authError,
    completeSetup,
    completingSetup,
    setupRequired,
    cancelSignIn,
    completeFirstRun,
    onboardingRequired,
    revalidateSession,
    signInAndRefresh,
    signOutAndRefresh,
    signingIn,
  };
}
