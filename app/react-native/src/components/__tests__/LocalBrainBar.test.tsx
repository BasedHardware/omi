/**
 * Render tests for LocalBrainBar.
 *
 * The logic in localBrainRouter.ts is covered by unit tests that never mount a
 * component, so every JSX path in this file was previously unexercised: the
 * styles object, the expand/collapse branch, the ringing banner, and the
 * permission-denied branch. A crash on mount or a bad style key would not have
 * failed anything.
 *
 * The native modules are mocked at the boundary. Neither exists outside a real
 * device build, and mocking them is what lets the component's own logic -- as
 * opposed to the bridge -- be tested here.
 *
 * render() is async in @testing-library/react-native 14, so every mount is
 * awaited. Omitting the await silently leaves `screen` empty and produces
 * "render function has not been called" rather than a useful failure.
 */
import React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
  cleanup,
} from '@testing-library/react-native';

// Prefixed `mock` because jest.mock factories are hoisted above const
// declarations and may only reference variables with that prefix.
const mockIsLocalBrainAvailable = jest.fn(() => false);
const mockIsCallDetectionAvailable = jest.fn(() => true);
const mockGetCallPermissions = jest.fn(async () => ({
  canDetect: true,
  canAnswer: false,
}));
const mockRequestCallPermissions = jest.fn(async () => ({
  canDetect: true,
  canAnswer: false,
}));
const mockStartCallDetection = jest.fn(
  async (_onState: (state: string, caller: string | null) => void) => true
);
const mockAnswerCall = jest.fn(async () => true);
const mockHangUp = jest.fn(async () => true);

// Both modules export isLocalBrainAvailable / isCallDetectionAvailable as
// BOOLEANS (`native != null`), so the mocks must too. Returning a thunk here
// would make every consumer treat a function as truthy -- which is exactly the
// bug this file initially had: the bar rendered "model not loaded" even with the
// native module absent, because `fn ? a : b` is always `a`.
//
// The getters exist because the factories are hoisted above the const
// declarations; a getter defers the read to access time, where the temporal dead
// zone is over. Passing the mocks by reference instead would read them while the
// factory runs and yield undefined.
jest.mock('../../../modules/local-brain', () => ({
  get isLocalBrainAvailable() {
    return mockIsLocalBrainAvailable();
  },
}));

jest.mock('../../../modules/local-calls', () => ({
  get isCallDetectionAvailable() {
    return mockIsCallDetectionAvailable();
  },
  isSupportedPlatform: true,
  getCallPermissions: () => mockGetCallPermissions(),
  requestCallPermissions: () => mockRequestCallPermissions(),
  startCallDetection: (...a: Parameters<typeof mockStartCallDetection>) =>
    mockStartCallDetection(...a),
  answerCall: () => mockAnswerCall(),
  hangUp: () => mockHangUp(),
}));

import { LocalBrainBar, type RouteTrace } from '../LocalBrainBar';

// RNTL auto-cleanup registers itself only when it can detect the test
// framework; without this, every render stays mounted and `screen` searches an
// ever-growing tree, which makes assertions depend on test order.
afterEach(() => {
  cleanup();
});

beforeEach(() => {
  jest.clearAllMocks();
  mockIsCallDetectionAvailable.mockReturnValue(true);
  mockGetCallPermissions.mockResolvedValue({ canDetect: true, canAnswer: false });
  mockRequestCallPermissions.mockResolvedValue({
    canDetect: true,
    canAnswer: false,
  });
});

const routerTrace: RouteTrace = {
  source: 'router',
  route: 'create_reminder',
  margin: 0.42,
};

/** Capture the callback the component hands to startCallDetection. */
function captureListener() {
  let emit: ((state: string) => void) | undefined;
  mockStartCallDetection.mockImplementation(
    async (cb: (state: string, caller: string | null) => void) => {
      emit = (state) => cb(state, null);
      return true;
    }
  );
  return () => emit;
}

describe('LocalBrainBar', () => {
  it('reports the router decision and the margin', async () => {
    await render(<LocalBrainBar trace={routerTrace} />);
    expect(screen.getByText(/routed/)).toBeTruthy();
    expect(screen.getByText(/reminder/)).toBeTruthy();
    expect(screen.getByText(/m0\.42/)).toBeTruthy();
  });

  it('distinguishes a heuristic decision from a router one', async () => {
    await render(
      <LocalBrainBar
        trace={{ source: 'heuristic', route: 'create_task', margin: 0 }}
      />
    );
    expect(screen.getByText(/heuristic/)).toBeTruthy();
  });

  it('says the native module is absent rather than rendering nothing', async () => {
    mockIsLocalBrainAvailable.mockReturnValue(false);
    await render(<LocalBrainBar />);
    expect(screen.getByText(/no native module/)).toBeTruthy();
  });

  it('hides the trace entirely when there is no decision yet', async () => {
    await render(<LocalBrainBar />);
    expect(screen.queryByText(/routed/)).toBeNull();
    expect(screen.queryByText(/heuristic/)).toBeNull();
  });

  it('keeps detail collapsed until tapped, then reveals the decline reason', async () => {
    await render(
      <LocalBrainBar
        trace={{
          source: 'heuristic',
          route: 'chat',
          margin: 0,
          reason: 'router declined',
        }}
      />
    );
    expect(screen.queryByText('router declined')).toBeNull();
    fireEvent.press(screen.getByText(/no native module/));
    await waitFor(() => expect(screen.getByText('router declined')).toBeTruthy());
  });

  it('does not ask for call permissions when the module is unavailable', async () => {
    mockIsCallDetectionAvailable.mockReturnValue(false);
    await render(<LocalBrainBar />);
    expect(mockRequestCallPermissions).not.toHaveBeenCalled();
  });

  it('does not start detection when the permission was refused', async () => {
    mockRequestCallPermissions.mockResolvedValue({
      canDetect: false,
      canAnswer: false,
    });
    await render(<LocalBrainBar />);
    await waitFor(() => expect(mockStartCallDetection).not.toHaveBeenCalled());
  });

  it('shows the incoming-call banner on a ring and clears it after hang up', async () => {
    const emit = captureListener();
    await render(<LocalBrainBar />);
    await waitFor(() => expect(emit()).toBeDefined());

    await act(async () => emit()?.('ringing'));
    expect(await screen.findByText('Incoming call')).toBeTruthy();

    // Wrapped in act because the handler awaits hangUp() and then setRinging;
    // unwrapped, that update lands after the press returns.
    await act(async () => {
      fireEvent.press(screen.getByText('Decline'));
    });
    await waitFor(() => expect(mockHangUp).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText('Incoming call')).toBeNull());
  });

  it('replaces Answer with a permission message instead of a dead button', async () => {
    const emit = captureListener();
    await render(<LocalBrainBar />);
    await waitFor(() => expect(emit()).toBeDefined());
    await act(async () => emit()?.('ringing'));

    expect(await screen.findByText(/answering needs permission/)).toBeTruthy();
    expect(screen.queryByText('Answer')).toBeNull();
  });

  it('offers Answer once the grant exists', async () => {
    const emit = captureListener();
    mockRequestCallPermissions.mockResolvedValue({
      canDetect: true,
      canAnswer: true,
    });
    mockGetCallPermissions.mockResolvedValue({ canDetect: true, canAnswer: true });
    await render(<LocalBrainBar />);
    await waitFor(() => expect(emit()).toBeDefined());
    await act(async () => emit()?.('ringing'));

    await act(async () => {
      fireEvent.press(await screen.findByText('Answer'));
    });
    await waitFor(() => expect(mockAnswerCall).toHaveBeenCalled());
  });
});
