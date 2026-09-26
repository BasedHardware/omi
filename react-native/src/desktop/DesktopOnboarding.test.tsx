import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {AppState, Linking, Text} from 'react-native';
import {DesktopOnboarding} from './DesktopOnboarding';
import {DesktopWindow} from './DesktopWindow';
import {Button} from '../ui/Button';
import {PermissionRow} from '../ui/PermissionRow';
import {OmiAvatar} from '../ui/OmiAvatar';
import {
  loadPermissionStatus,
  requestDesktopPermission,
} from '../desktopSettingsClient';

jest.mock('../desktopSettingsClient', () => ({
  loadPermissionStatus: jest.fn(async () => ({
    screen: 'unknown',
    microphone: 'unknown',
    notifications: 'unknown',
  })),
  requestDesktopPermission: jest.fn(async () => 'denied'),
}));
jest.mock('../ui/OmiAvatar', () => ({OmiAvatar: () => null}));
jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));
let renderer: Renderer.ReactTestRenderer;
const signIn = jest.fn();
const complete = jest.fn();
function content() {
  return renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
}
async function mount(
  props: Partial<React.ComponentProps<typeof DesktopOnboarding>> = {},
) {
  await act(async () => {
    renderer = Renderer.create(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        onCompleteSetup={complete}
        {...props}
      />,
    );
  });
}
async function press(label: string) {
  await act(async () => {
    const button = renderer.root.findAll(node => {
      if (typeof node.props.onPress !== 'function') {
        return false;
      }
      const named = String(node.props.accessibilityLabel ?? '');
      const child = String(node.props.children ?? '');
      return named === label || child === label || named.includes(label);
    })[0];
    expect(button).toBeDefined();
    expect(button!.props.disabled).not.toBe(true);
    button!.props.onPress();
  });
}
beforeEach(() => {
  jest.spyOn(AppState, 'addEventListener').mockReturnValue({remove: jest.fn()});
});
afterEach(() => {
  act(() => renderer?.unmount());
  jest.clearAllMocks();
  jest.restoreAllMocks();
  jest.useRealTimers();
});

test('explains privacy before sign-in, handles auth transition, and finishes only by agreement', async () => {
  await mount();
  expect(requestDesktopPermission).not.toHaveBeenCalled();
  await press('Get started');
  expect(content()).toContain('Cloud AI services');
  expect(content()).toContain('you read it back from Home');
  expect(signIn).not.toHaveBeenCalled();
  await press('Continue');
  expect(content()).toMatch(/Step\s+2\s+of\s+7/);
  await press('Sign in');
  expect(signIn).toHaveBeenCalledTimes(1);
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        setupRequired
        onCompleteSetup={complete}
      />,
    ),
  );
  expect(content()).toContain('Now the permissions.');
  expect(content()).toMatch(/Step\s+3\s+of\s+7/);
  expect(loadPermissionStatus).toHaveBeenCalledTimes(1);
  expect(requestDesktopPermission).not.toHaveBeenCalled();
  await press("I'll do these later");
  expect(content()).toContain('Meet your next collaborators.');
  expect(content()).toContain('AI assistants');
  expect(content()).toContain('OpenClaw');
  expect(content()).not.toContain('Local files');
  await press('Explore OpenClaw');
  expect(content()).toContain('No account has been connected');
  await press('Continue');
  expect(content()).toContain('Connect data');
  expect(content()).toContain('Local files');
  expect(content()).toContain('X (Twitter)');
  expect(content()).not.toContain('OpenClaw');
  expect(content()).not.toContain('Connect Claude when you are ready');
  await press('Back');
  expect(content()).toContain('OpenClaw');
  await press('Continue');
  await press('Continue');
  expect(content()).toContain('A quick look around');
  await press('Continue');
  expect(complete).not.toHaveBeenCalled();
  await press('Agree and continue');
  expect(complete).toHaveBeenCalledWith(false);
});

test('restored accounts skip sign-in, permission denial and failure never block continuing', async () => {
  await mount({setupRequired: true});
  await press('Get started');
  await press('Continue');
  await press('Screen.');
  expect(renderer.root.findByType(DesktopWindow).props.presentation).toBe(
    'permission-guide',
  );
  expect(content()).not.toContain('Permission granted');
  expect(renderer.root.findByType(OmiAvatar).props.motion).toBe('breathe');
  await press('Back to setup');
  expect(content()).toContain('Open Settings');
  jest
    .mocked(requestDesktopPermission)
    .mockRejectedValueOnce(new Error('private native error'));
  await press('Screen.');
  expect(content()).toContain('Permission request failed');
  expect(renderer.root.findByType(OmiAvatar).props.motion).toBeUndefined();
  expect(content()).not.toContain('private native error');
  await press('Back to setup');
  expect(renderer.root.findByType(DesktopWindow).props.presentation).toBe(
    'onboarding',
  );
  await press("I'll do these later");
  expect(content()).toContain('Meet your next collaborators.');
  expect(signIn).not.toHaveBeenCalled();
});

test('late permission completion cannot change a retired account or block the later escape', async () => {
  let release!: (value: 'granted') => void;
  jest.mocked(requestDesktopPermission).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  await mount({setupRequired: true});
  await press('Get started');
  await press('Continue');
  await press('Screen.');
  expect(content()).toContain('Checking macOS permission');
  await press('Back to setup');
  await press("I'll do these later");
  await act(async () =>
    renderer.update(<DesktopOnboarding onSignIn={signIn} signingIn={false} />),
  );
  await act(async () => release('granted'));
  expect(content()).toContain('Welcome to Omi');
  expect(renderer.root.findByType(DesktopWindow).props.presentation).toBe(
    'onboarding',
  );
  expect(content()).not.toContain('Allowed');
  expect(complete).not.toHaveBeenCalled();
});

test('sign-in cancellation and setup failure preserve retry controls without automatic completion', async () => {
  const cancel = jest.fn();
  await mount();
  await press('Get started');
  await press('Continue');
  await act(async () =>
    renderer.update(
      <DesktopOnboarding onSignIn={signIn} signingIn onCancelSignIn={cancel} />,
    ),
  );
  await press('Cancel sign in');
  expect(cancel).toHaveBeenCalledTimes(1);
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        setupRequired
        onCompleteSetup={complete}
      />,
    ),
  );
  await press("I'll do these later");
  await press('Continue');
  await press('Continue');
  await press('Continue');
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        setupRequired
        completingSetup
        onCompleteSetup={complete}
      />,
    ),
  );
  expect(
    renderer.root
      .findAllByType(Button)
      .find(node => node.props.children === 'Saving…')!.props.disabled,
  ).toBe(true);
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        setupRequired
        error="Could not save setup"
        onCompleteSetup={complete}
      />,
    ),
  );
  expect(content()).toContain('Could not save setup');
  await press('Agree and continue');
  expect(complete).toHaveBeenCalledTimes(1);
});

test('Settings return refreshes actual grants without advancing; polling stops on leaving', async () => {
  jest.useFakeTimers();
  const subscription = jest.spyOn(AppState, 'addEventListener');
  await mount({setupRequired: true});
  await press('Get started');
  await press('Continue');
  await press('Screen.');
  expect(content()).toContain('Privacy & Security → Screen Recording');
  jest.mocked(loadPermissionStatus).mockResolvedValueOnce({
    screen: 'granted',
    microphone: 'denied',
    notifications: 'unknown',
  });
  const onReturn = subscription.mock.calls.find(
    ([event]) => event === 'change',
  )![1];
  await act(async () => onReturn('active'));
  expect(content()).toContain('Permission granted');
  expect(renderer.root.findByType(OmiAvatar).props).toMatchObject({
    motion: 'success',
    motionKey: 'screen',
    reduceMotion: true,
  });
  // Confirmation cannot dismiss or resize the user's guide, or advance setup.
  expect(renderer.root.findByType(DesktopWindow).props.presentation).toBe(
    'permission-guide',
  );
  expect(complete).not.toHaveBeenCalled();
  await press('Back to setup');
  const rows = renderer.root.findAllByType(PermissionRow);
  expect(rows.map(row => row.props.granted)).toEqual([true, false, false]);
  expect(rows[0].props.disabled).toBe(true);
  expect(content()).toContain('Now the permissions.');
  expect(complete).not.toHaveBeenCalled();
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
  expect(loadPermissionStatus).toHaveBeenCalledTimes(3);
  await press("I'll do these later");
  await act(async () => {
    jest.advanceTimersByTime(4500);
  });
  expect(loadPermissionStatus).toHaveBeenCalledTimes(3);
});

test('a late poll from a retired permission step cannot replace a new step status', async () => {
  jest.useFakeTimers();
  let release!: (value: {
    screen: 'granted';
    microphone: 'granted';
    notifications: 'granted';
  }) => void;
  await mount({setupRequired: true});
  await press('Get started');
  await press('Continue');
  jest.mocked(loadPermissionStatus).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        release = resolve;
      }),
  );
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
  await press("I'll do these later");
  await press('Back');
  await act(async () =>
    release({
      screen: 'granted',
      microphone: 'granted',
      notifications: 'granted',
    }),
  );
  expect(
    renderer.root.findAllByType(PermissionRow).map(row => row.props.granted),
  ).toEqual([false, false, false]);
  expect(complete).not.toHaveBeenCalled();
});

test('a poll begun during a permission prompt cannot overwrite its newer grant', async () => {
  jest.useFakeTimers();
  let grant!: (value: 'granted') => void;
  let stalePoll!: (value: {
    screen: 'denied';
    microphone: 'unknown';
    notifications: 'unknown';
  }) => void;
  await mount({setupRequired: true});
  await press('Get started');
  await press('Continue');
  jest.mocked(requestDesktopPermission).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        grant = resolve;
      }),
  );
  await press('Screen.');
  jest.mocked(loadPermissionStatus).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        stalePoll = resolve;
      }),
  );
  await act(async () => {
    jest.advanceTimersByTime(1500);
  });
  await act(async () => grant('granted'));
  await act(async () =>
    stalePoll({
      screen: 'denied',
      microphone: 'unknown',
      notifications: 'unknown',
    }),
  );
  expect(content()).toContain('Permission granted');
  await press('Back to setup');
  expect(renderer.root.findAllByType(PermissionRow)[0].props.granted).toBe(
    true,
  );
  expect(content()).toContain('Now the permissions.');
});

test('the mark greets on demand and changes gesture with the step, without advancing it', async () => {
  await mount();
  expect(renderer.root.findByType(OmiAvatar).props).toMatchObject({
    motion: 'arrive',
    motionKey: 'welcome:0',
  });
  await press('Say hello to Omi');
  expect(renderer.root.findByType(OmiAvatar).props.motionKey).toBe('welcome:1');
  expect(signIn).not.toHaveBeenCalled();
  await press('Get started');
  expect(renderer.root.findByType(OmiAvatar).props).toMatchObject({
    motion: 'gather',
    motionKey: 'value:1',
  });
});

test('desktop handoff shows the confirmation code and reopens the browser page while signing in', async () => {
  const openURL = jest
    .spyOn(Linking, 'openURL')
    .mockResolvedValue(undefined as never);
  await mount();
  await press('Get started');
  await press('Continue');
  await press('Sign in');
  expect(signIn).toHaveBeenCalledTimes(1);
  // Before the native start lands there is no code to show.
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn
        onCompleteSetup={complete}
      />,
    ),
  );
  expect(content()).not.toContain('sign-in code');
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn
        onCompleteSetup={complete}
        desktopHandoff={{
          code: '418293',
          expiresAt: Date.now() + 300_000,
          browserUrl:
            'https://omi-v5-backend-staging.example.workers.dev/auth/desktop?desktop_auth=abc',
        }}
      />,
    ),
  );
  expect(content()).toContain('418293');
  expect(content()).toContain(
    'Finish in your browser, then enter this code on the Omi sign-in page.',
  );
  await press('Open the sign-in page again');
  expect(openURL).toHaveBeenCalledWith(
    'https://omi-v5-backend-staging.example.workers.dev/auth/desktop?desktop_auth=abc',
  );
  // Once the attempt ends the code must not linger on the surface.
  await act(async () =>
    renderer.update(
      <DesktopOnboarding
        onSignIn={signIn}
        signingIn={false}
        onCompleteSetup={complete}
      />,
    ),
  );
  expect(content()).not.toContain('418293');
  expect(content()).not.toContain('sign-in code');
  openURL.mockRestore();
});
