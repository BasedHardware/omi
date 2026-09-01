import React from 'react';
import ReactTestRenderer from 'react-test-renderer';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
};

jest.mock('../src/omiNative', () => ({
  omiAuth: {
    hasCloudSession: () => mockAuth.hasCloudSession(),
    hasCompletedOnboarding: () => mockAuth.hasCompletedOnboarding(),
    markOnboardingComplete: () => mockAuth.markOnboardingComplete(),
    signIn: () => mockAuth.signIn(),
    signOut: () => mockAuth.signOut(),
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
  mockAuth.hasCloudSession.mockReset();
  mockAuth.hasCompletedOnboarding.mockReset();
  mockAuth.markOnboardingComplete.mockReset();
  mockAuth.signIn.mockReset();
  mockAuth.signOut.mockReset();
  mockAuth.markOnboardingComplete.mockResolvedValue(undefined);
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
