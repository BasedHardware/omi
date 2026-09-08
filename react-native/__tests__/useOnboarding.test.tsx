import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async (): Promise<void> => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
  cancelSignIn: jest.fn(async () => undefined),
};
let mockBackendSessionInvalidatedListener: (() => void) | undefined;

jest.mock('../src/omiNative', () => ({
  omiAuth: {
    hasCloudSession: () => mockAuth.hasCloudSession(),
    hasCompletedOnboarding: () => mockAuth.hasCompletedOnboarding(),
    markOnboardingComplete: () => mockAuth.markOnboardingComplete(),
    signIn: () => mockAuth.signIn(),
    signOut: () => mockAuth.signOut(),
    cancelSignIn: () => mockAuth.cancelSignIn(),
  },
  subscribeOmiBackendSessionInvalidated: (listener: () => void) => {
    mockBackendSessionInvalidatedListener = listener;
    return () => {
      mockBackendSessionInvalidatedListener = undefined;
    };
  },
}));

import {
  SESSION_UNREACHABLE_COPY,
  useOnboarding,
} from '../src/app/useOnboarding';

function Harness({
  macDesktop,
  refreshReads,
  onState,
}: {
  macDesktop: boolean;
  refreshReads: (
    initial: boolean,
    options?: {ignoreEnabled?: boolean},
  ) => Promise<void>;
  onState: (state: ReturnType<typeof useOnboarding>) => void;
}) {
  const state = useOnboarding(macDesktop, refreshReads);
  onState(state);
  return null;
}

async function renderOnboarding(
  macDesktop: boolean,
  refreshReads: (
    initial: boolean,
    options?: {ignoreEnabled?: boolean},
  ) => Promise<void> = async () => undefined,
) {
  let latest: ReturnType<typeof useOnboarding> | null = null;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(
      <Harness
        macDesktop={macDesktop}
        onState={state => {
          latest = state;
        }}
        refreshReads={refreshReads}
      />,
    );
  });
  return {
    latest: () => latest!,
    update: async (next: boolean) => {
      await ReactTestRenderer.act(async () => {
        renderer.update(
          <Harness
            macDesktop={next}
            onState={state => {
              latest = state;
            }}
            refreshReads={refreshReads}
          />,
        );
      });
    },
  };
}

beforeEach(() => {
  mockBackendSessionInvalidatedListener = undefined;
  mockAuth.hasCloudSession.mockReset();
  mockAuth.hasCompletedOnboarding.mockReset();
  mockAuth.markOnboardingComplete.mockReset();
  mockAuth.signIn.mockReset();
  mockAuth.signOut.mockReset();
  mockAuth.cancelSignIn.mockClear();
  mockAuth.markOnboardingComplete.mockResolvedValue(undefined);
});

test('a native 401 invalidation re-probes and leaves the ready shell', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true).mockResolvedValue(false);

  const hook = await renderOnboarding(true);
  expect(hook.latest().onboardingRequired).toBe(false);

  await ReactTestRenderer.act(async () => {
    mockBackendSessionInvalidatedListener?.();
    await Promise.resolve();
  });

  expect(hook.latest().onboardingRequired).toBe(true);
});

test('completed onboarding without a cloud session still requires Sign in', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(false);

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(true);
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
});

test('a live cloud session resumes unfinished setup without marking consent', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().setupRequired).toBe(true);
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
});

test('session probe settles from auth alone when native devices are unavailable', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(false);
  expect(hook.latest().onboardingRequired).not.toBeNull();
});

test('an unreachable startup probe keeps Welcome with an unreachable error', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockRejectedValue(new Error('offline'));

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().authError).toBe(SESSION_UNREACHABLE_COPY);
});

test('a recovered startup probe clears the unreachable error', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockRejectedValueOnce(new Error('offline'));

  const hook = await renderOnboarding(true);
  expect(hook.latest().authError).toBe(SESSION_UNREACHABLE_COPY);

  mockAuth.hasCloudSession.mockResolvedValue(true);
  await hook.update(false);
  expect(hook.latest().onboardingRequired).toBe(false);
  expect(hook.latest().authError).toBeNull();
});

test('sign-in requires explicit setup completion before cloud reads', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);
  expect(hook.latest().onboardingRequired).toBe(true);

  await ReactTestRenderer.act(async () => {
    await hook.latest().completeFirstRun();
  });

  expect(mockAuth.signIn).toHaveBeenCalledTimes(1);
  expect(hook.latest().setupRequired).toBe(true);
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
  expect(refreshReads).not.toHaveBeenCalled();
  mockAuth.hasCloudSession.mockResolvedValue(true);
  await ReactTestRenderer.act(async () => {
    await hook.latest().completeSetup();
  });
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(hook.latest().onboardingRequired).toBe(false);
  expect(refreshReads).toHaveBeenCalledWith(false, {ignoreEnabled: true});
});

test('a cancelled sign-in stays on Welcome without faking a session', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: false});
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signInAndRefresh();
  });

  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().authError).toBe('Sign in was not completed. Try again.');
  expect(refreshReads).not.toHaveBeenCalled();
});

test('a rejected sign-in stays on Welcome and stops the busy flag', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockRejectedValue(new Error('OMI_AUTH_UNAUTHORIZED'));
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);

  await ReactTestRenderer.act(async () => {
    await hook
      .latest()
      .signInAndRefresh()
      .catch(() => undefined);
  });

  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().signingIn).toBe(false);
  expect(hook.latest().authError).toBe('Sign in was not completed. Try again.');
});

test('a reads failure after a resumed sign-in keeps the shell without a sign-in error', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  const refresh = jest.fn(async () => {
    throw new Error('reads down');
  });

  const hook = await renderOnboarding(true, refresh);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signInAndRefresh();
  });

  expect(hook.latest().onboardingRequired).toBe(false);
  expect(hook.latest().signingIn).toBe(false);
  expect(hook.latest().authError).not.toBe(
    'Sign in was not completed. Try again.',
  );
  expect(hook.latest().authError).toBeNull();
  expect(refresh).toHaveBeenCalledWith(false, {ignoreEnabled: true});
});

test('sign-out returns the desktop to Welcome without firing cloud reads', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true).mockResolvedValue(false);
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);
  expect(hook.latest().onboardingRequired).toBe(false);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signOutAndRefresh();
  });

  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  expect(hook.latest().onboardingRequired).toBe(true);
  // A signed-out Mac must not hit the cloud; a late refresh could otherwise
  // overwrite the next session's fresh load.
  expect(refreshReads).not.toHaveBeenCalled();
});

test('revalidateSession falls back to Welcome once the keychain session is gone', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true).mockResolvedValue(false);
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);
  expect(hook.latest().onboardingRequired).toBe(false);

  // The native refresh cleared the keychain mid-run; a chat/read 401 triggers
  // a re-probe and the gate must leave the product shell.
  mockAuth.hasCloudSession.mockResolvedValue(false);
  await ReactTestRenderer.act(async () => {
    await hook.latest().revalidateSession();
  });
  expect(hook.latest().onboardingRequired).toBe(true);
});

test('revalidateSession keeps a live session in the shell', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  const refreshReads = jest.fn(async () => undefined);

  const hook = await renderOnboarding(true, refreshReads);
  expect(hook.latest().onboardingRequired).toBe(false);

  await ReactTestRenderer.act(async () => {
    await hook.latest().revalidateSession();
  });
  expect(hook.latest().onboardingRequired).toBe(false);
});

test('a late revalidation cannot eject a newer signed-in session', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  const hook = await renderOnboarding(true);
  let resolveLate: ((hasSession: boolean) => void) | undefined;
  mockAuth.hasCloudSession
    .mockImplementationOnce(
      () =>
        new Promise<boolean>(resolve => {
          resolveLate = resolve;
        }),
    )
    .mockResolvedValueOnce(false);

  const late = hook.latest().revalidateSession();
  await ReactTestRenderer.act(async () => {
    await hook.latest().revalidateSession();
  });
  expect(hook.latest().onboardingRequired).toBe(true);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signInAndRefresh();
  });
  expect(hook.latest().onboardingRequired).toBe(false);

  await ReactTestRenderer.act(async () => {
    resolveLate!(false);
    await late;
  });
  expect(hook.latest().onboardingRequired).toBe(false);
});

test('a late startup probe cannot eject a newer signed-in session', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  let resolveProbe: ((hasSession: boolean) => void) | undefined;
  mockAuth.hasCloudSession.mockImplementationOnce(
    () =>
      new Promise<boolean>(resolve => {
        resolveProbe = resolve;
      }),
  );
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  const hook = await renderOnboarding(true);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signInAndRefresh();
  });
  expect(hook.latest().onboardingRequired).toBe(false);

  await ReactTestRenderer.act(async () => {
    resolveProbe!(false);
  });
  expect(hook.latest().onboardingRequired).toBe(false);
});

test('sign-out retires a pending sign-in without leaving Welcome busy', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  let resolveSignIn: ((result: {signedIn: boolean}) => void) | undefined;
  mockAuth.signIn.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        resolveSignIn = resolve;
      }),
  );
  const hook = await renderOnboarding(true);
  let pending: Promise<void>;
  await ReactTestRenderer.act(async () => {
    pending = hook.latest().signInAndRefresh();
  });
  expect(hook.latest().signingIn).toBe(true);

  await ReactTestRenderer.act(async () => {
    await hook.latest().signOutAndRefresh();
    resolveSignIn!({signedIn: false});
    await pending;
  });
  expect(hook.latest().signingIn).toBe(false);
  expect(hook.latest().onboardingRequired).toBe(true);
});

test('a Mac without the native auth module stays on Welcome instead of faking ready', async () => {
  jest.resetModules();
  jest.doMock('../src/omiNative', () => ({
    omiAuth: null,
    subscribeOmiBackendSessionInvalidated: () => () => undefined,
  }));
  const {useOnboarding: missingAuthHook} = require('../src/app/useOnboarding');

  let latest: ReturnType<typeof missingAuthHook> | null = null;
  await ReactTestRenderer.act(async () => {
    ReactTestRenderer.create(
      <Harness
        macDesktop={true}
        onState={state => {
          latest = state;
        }}
        refreshReads={async () => undefined}
      />,
    );
  });
  expect(latest!.onboardingRequired).toBe(true);
  jest.dontMock('../src/omiNative');
});

test('cancel retires a pending sign-in without clearing or accepting a session', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  let resolveSignIn!: (value: {signedIn: boolean}) => void;
  mockAuth.signIn.mockImplementation(
    () =>
      new Promise(resolve => {
        resolveSignIn = resolve;
      }),
  );
  const refresh = jest.fn(async () => undefined);
  const hook = await renderOnboarding(true, refresh);
  let pending!: Promise<void>;
  await ReactTestRenderer.act(async () => {
    pending = hook.latest().signInAndRefresh();
  });
  expect(hook.latest().signingIn).toBe(true);
  await ReactTestRenderer.act(async () => {
    await hook.latest().cancelSignIn();
  });
  expect(mockAuth.cancelSignIn).toHaveBeenCalledTimes(1);
  expect(hook.latest().signingIn).toBe(false);
  await ReactTestRenderer.act(async () => {
    resolveSignIn({signedIn: true});
    await pending;
  });
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
  expect(mockAuth.signOut).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
});

test('web setup requires disclosure but never invents native sign-in', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  const refresh = jest.fn(async () => undefined);
  const hook = await renderOnboarding(false, refresh);
  expect(hook.latest().setupRequired).toBe(true);
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(mockAuth.hasCloudSession).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => {
    await hook.latest().completeSetup();
  });
  expect(hook.latest().onboardingRequired).toBe(false);
  expect(mockAuth.signIn).not.toHaveBeenCalled();
  expect(refresh).toHaveBeenCalledTimes(1);
});

test('failed setup persistence stays on disclosure and can retry', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.markOnboardingComplete.mockRejectedValueOnce(new Error('storage'));
  const refresh = jest.fn(async () => undefined);
  const hook = await renderOnboarding(true, refresh);
  await ReactTestRenderer.act(async () => {
    await hook.latest().completeSetup();
  });
  expect(hook.latest().setupRequired).toBe(true);
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().completingSetup).toBe(false);
  expect(refresh).not.toHaveBeenCalled();
  await ReactTestRenderer.act(async () => {
    await hook.latest().completeSetup();
  });
  expect(hook.latest().onboardingRequired).toBe(false);
});

test('a reads failure after consent still completes onboarding without a save error', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  const refresh = jest.fn(async () => {
    throw new Error('reads down');
  });

  const hook = await renderOnboarding(true, refresh);
  let completed!: boolean;
  await ReactTestRenderer.act(async () => {
    completed = await hook.latest().completeSetup();
  });

  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(completed).toBe(true);
  expect(hook.latest().setupRequired).toBe(false);
  expect(hook.latest().onboardingRequired).toBe(false);
  expect(hook.latest().completingSetup).toBe(false);
  expect(hook.latest().authError).not.toBe(
    'Setup could not be saved. Try again.',
  );
  expect(hook.latest().authError).toBeNull();
  expect(refresh).toHaveBeenCalledWith(false, {ignoreEnabled: true});
});

test('sign-out retires delayed setup completion without refreshing', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  let resolveSave!: () => void;
  mockAuth.markOnboardingComplete.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        resolveSave = resolve;
      }),
  );
  const refresh = jest.fn(async () => undefined);
  const hook = await renderOnboarding(true, refresh);
  let pending!: Promise<boolean>;
  await ReactTestRenderer.act(async () => {
    pending = hook.latest().completeSetup();
  });
  mockAuth.hasCloudSession.mockResolvedValue(false);
  await ReactTestRenderer.act(async () => {
    await hook.latest().signOutAndRefresh();
  });
  await ReactTestRenderer.act(async () => {
    resolveSave();
    await pending;
  });
  expect(hook.latest().onboardingRequired).toBe(true);
  expect(hook.latest().setupRequired).toBe(false);
  expect(refresh).not.toHaveBeenCalled();
});
