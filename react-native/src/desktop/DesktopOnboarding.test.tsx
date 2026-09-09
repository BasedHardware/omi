import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import {DesktopOnboarding} from './DesktopOnboarding';
import {Button} from '../ui/Button';
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
    const button = renderer.root
      .findAllByType(Button)
      .find(
        node =>
          node.props.accessibilityLabel === label ||
          node.props.children === label,
      );
    expect(button).toBeDefined();
    expect(button!.props.disabled).not.toBe(true);
    button!.props.onPress();
  });
}
afterEach(() => {
  act(() => renderer?.unmount());
  jest.clearAllMocks();
});

test('explains privacy before sign-in, handles auth transition, and finishes only by agreement', async () => {
  await mount();
  expect(requestDesktopPermission).not.toHaveBeenCalled();
  await press('Get started');
  expect(content()).toContain('Cloud AI services');
  expect(signIn).not.toHaveBeenCalled();
  await press('Continue');
  expect(content()).toMatch(/Step\s+2\s+of\s+5/);
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
  expect(content()).toContain('Choose what Omi can access');
  expect(content()).toMatch(/Step\s+3\s+of\s+5/);
  expect(loadPermissionStatus).toHaveBeenCalledTimes(1);
  expect(requestDesktopPermission).not.toHaveBeenCalled();
  await press('Continue without more permissions');
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
  await press('Allow screen recording');
  expect(content()).toContain('Not allowed');
  jest
    .mocked(requestDesktopPermission)
    .mockRejectedValueOnce(new Error('private native error'));
  await press('Allow screen recording');
  expect(content()).toContain('Permission request failed');
  expect(content()).not.toContain('private native error');
  await press('Continue without more permissions');
  expect(content()).toContain('A quick look around');
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
  await press('Allow screen recording');
  expect(content()).toContain('Waiting for macOS');
  await press('Continue without more permissions');
  await act(async () =>
    renderer.update(<DesktopOnboarding onSignIn={signIn} signingIn={false} />),
  );
  await act(async () => release('granted'));
  expect(content()).toContain('Welcome to Omi');
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
  await press('Continue without more permissions');
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
