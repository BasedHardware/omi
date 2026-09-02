import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text, TextInput} from 'react-native';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
};
const mockBackend = {
  request: jest.fn(async () => ({id: 'probe', status: 501, body: null})),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(async () => undefined),
};

jest.mock('../src/omiNative', () => ({
  omiAuth: mockAuth,
  omiBackend: mockBackend,
  omiNative: undefined,
  isNativeModuleInstalled: false,
  isNativeBackendInstalled: true,
  subscribeOmiNativeEvents: () => () => undefined,
}));

jest.mock('../src/app/useReduceMotion', () => ({
  useReduceMotion: () => true,
}));

// The macOS orchestrator branch keys off Platform.OS, so pin it before the
// orchestrator module loads.
const ReactNative = require('react-native');
Object.defineProperty(ReactNative.Platform, 'OS', {get: () => 'macos'});

const App = require('../src/app/AppOrchestrator').default;

function labelsOf(renderer: ReactTestRenderer.ReactTestRenderer): string[] {
  return renderer.root
    .findAll(node => typeof node.props.accessibilityLabel === 'string')
    .map(node => node.props.accessibilityLabel);
}

function textOf(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

beforeEach(() => {
  mockAuth.hasCloudSession.mockReset();
  mockAuth.hasCompletedOnboarding.mockReset();
  mockAuth.markOnboardingComplete.mockReset();
  mockAuth.markOnboardingComplete.mockResolvedValue(undefined);
  mockAuth.signIn.mockReset();
  mockAuth.signOut.mockReset();
  mockBackend.request.mockClear();
});

afterEach(() => {
  act(() => {
    renderers.splice(0).forEach(renderer => renderer.unmount());
  });
});

async function renderApp() {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<App />);
  });
  renderers.push(renderer!);
  return renderer!;
}

test('an unsettled probe paints an empty window with no product IA', async () => {
  mockAuth.hasCompletedOnboarding.mockReturnValue(new Promise(() => undefined));
  mockAuth.hasCloudSession.mockReturnValue(new Promise(() => undefined));

  const renderer = await renderApp();
  const labels = labelsOf(renderer);
  expect(labels).toContain('Desktop workspace material');
  expect(labels).toContain('Session check');
  expect(labels).not.toContain('Omi desktop chrome');
  expect(labels).not.toContain('Omi desktop');
  expect(labels).not.toContain('First-run onboarding');
  for (const nav of ['Home', 'Conversations', 'Tasks', 'Apps', 'Settings']) {
    expect(labels).not.toContain(nav);
  }
  expect(renderer.root.findAllByType(Text)).toHaveLength(0);
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(0);
});

test('signed-out Mac sees only the Welcome until a real session lands', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  mockAuth.signOut.mockResolvedValue({signedOut: true});

  const renderer = await renderApp();
  let labels = labelsOf(renderer);
  expect(labels).toContain('First-run onboarding');
  expect(textOf(renderer)).toContain('Welcome to Omi');
  // No nav pills, no omnibar, no Home currents, no Settings gear.
  for (const nav of ['Home', 'Conversations', 'Tasks', 'Apps', 'Settings']) {
    expect(labels).not.toContain(nav);
  }
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(0);
  expect(labels).not.toContain('Home currents');
  expect(labels).not.toContain('Home tasks');
  expect(textOf(renderer)).not.toContain('Chat is temporarily unavailable.');

  // A real native sign-in persists: completion is recorded, reads refresh,
  // and the full chrome takes over.
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  expect(mockAuth.signIn).toHaveBeenCalledTimes(1);
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  labels = labelsOf(renderer);
  expect(labels).not.toContain('First-run onboarding');
  expect(labels).toContain('Omi desktop chrome');
  expect(labels).toContain('Home currents');
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");

  // Signing out clears the session and returns to the same Welcome.
  mockAuth.hasCloudSession.mockResolvedValue(false);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign out')
      .props.onPress();
  });
  expect(mockAuth.signOut).toHaveBeenCalledTimes(1);
  labels = labelsOf(renderer);
  expect(labels).toContain('First-run onboarding');
  expect(labels).not.toContain('Omi desktop chrome');
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(0);
});

test('a cancelled native sign-in keeps the Welcome up without faking ready', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: false});

  const renderer = await renderApp();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  const labels = labelsOf(renderer);
  expect(labels).toContain('First-run onboarding');
  expect(labels).not.toContain('Omi desktop chrome');
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
});
