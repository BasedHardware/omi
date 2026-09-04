import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
};
let mockBackendSessionInvalidatedListener: (() => void) | undefined;

jest.mock('../src/omiNative', () => ({
  omiAuth: {
    hasCloudSession: () => mockAuth.hasCloudSession(),
    hasCompletedOnboarding: () => mockAuth.hasCompletedOnboarding(),
    markOnboardingComplete: () => mockAuth.markOnboardingComplete(),
    signIn: () => mockAuth.signIn(),
    signOut: () => mockAuth.signOut(),
  },
  subscribeOmiBackendSessionInvalidated: (listener: () => void) => {
    mockBackendSessionInvalidatedListener = listener;
    return () => {
      mockBackendSessionInvalidatedListener = undefined;
    };
  },
}));

import {useOnboarding} from '../src/app/useOnboarding';

function Harness({
  macDesktop,
  refreshReads,
  onState,
}: {
  macDesktop: boolean;
  refreshReads: (initial: boolean) => Promise<void>;
  onState: (state: ReturnType<typeof useOnboarding>) => void;
}) {
  const state = useOnboarding(macDesktop, refreshReads);
  onState(state);
  return null;
}

async function renderOnboarding(
  macDesktop: boolean,
  refreshReads: (initial: boolean) => Promise<void> = async () => undefined,
) {
  let latest: ReturnType<typeof useOnboarding> | null = null;
  await ReactTestRenderer.act(async () => {
    ReactTestRenderer.create(
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
  };
}

beforeEach(() => {
  mockBackendSessionInvalidatedListener = undefined;
  mockAuth.hasCloudSession.mockReset();
  mockAuth.hasCompletedOnboarding.mockReset();
  mockAuth.markOnboardingComplete.mockReset();
  mockAuth.signIn.mockReset();
  mockAuth.signOut.mockReset();
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

test('a live cloud session leaves DesktopApp ready even before onboarding is marked', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(false);
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalled();
});

test('session probe settles from auth alone when native devices are unavailable', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const hook = await renderOnboarding(true);

  expect(hook.latest().onboardingRequired).toBe(false);
  expect(hook.latest().onboardingRequired).not.toBeNull();
});

test('a real sign-in records onboarding completion and leaves Welcome', async () => {
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
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  expect(hook.latest().onboardingRequired).toBe(false);
  expect(refreshReads).toHaveBeenCalledWith(false);
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
