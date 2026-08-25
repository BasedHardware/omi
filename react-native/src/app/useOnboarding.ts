import {useCallback, useEffect, useState} from 'react';
import {omiAuth} from '../omiNative';

export function useOnboarding(
  macDesktop: boolean,
  refreshReads: (initial: boolean) => Promise<void>,
) {
  const [signingIn, setSigningIn] = useState(false);
  const [onboardingRequired, setOnboardingRequired] = useState(macDesktop);

  useEffect(() => {
    let active = true;
    const auth = omiAuth;
    if (!macDesktop || auth === undefined || auth === null) {
      setOnboardingRequired(false);
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
          setOnboardingRequired(!completed && !hasSession);
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

  const signInAndRefresh = useCallback(async () => {
    if (omiAuth === undefined || omiAuth === null) {
      return;
    }
    setSigningIn(true);
    try {
      const result = await omiAuth.signIn();
      if (result.signedIn) {
        await omiAuth.markOnboardingComplete();
        await refreshReads(false);
      }
    } finally {
      setSigningIn(false);
    }
  }, [refreshReads]);

  const completeFirstRun = useCallback(async () => {
    if (omiAuth === undefined || omiAuth === null) {
      return;
    }
    setSigningIn(true);
    try {
      const result = await omiAuth.signIn();
      if (result.signedIn) {
        await omiAuth.markOnboardingComplete();
        setOnboardingRequired(false);
        await refreshReads(false);
      }
    } finally {
      setSigningIn(false);
    }
  }, [refreshReads]);

  return {
    completeFirstRun,
    onboardingRequired,
    signInAndRefresh,
    signingIn,
  };
}
