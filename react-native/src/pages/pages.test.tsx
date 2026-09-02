import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
};
const mockBackend = {
  request: jest.fn(),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(async () => undefined),
};

jest.mock('../omiNative', () => ({
  omiAuth: mockAuth,
  omiBackend: mockBackend,
}));

const {ConnectorsPage} = require('./Connectors');
const {SettingsPage} = require('./Settings');

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

function labelsOf(renderer: ReactTestRenderer.ReactTestRenderer): string[] {
  return renderer.root
    .findAll(node => typeof node.props.accessibilityLabel === 'string')
    .map(node => node.props.accessibilityLabel);
}

const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

afterEach(() => {
  act(() => {
    renderers.splice(0).forEach(renderer => renderer.unmount());
  });
  mockAuth.hasCloudSession.mockReset();
  mockBackend.request.mockReset();
});

async function renderPage(Page: typeof ConnectorsPage) {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<Page onSignIn={jest.fn()} />);
  });
  renderers.push(renderer!);
  return renderer!;
}

test('a rejected session probe keeps apps retryable instead of loading forever', async () => {
  mockAuth.hasCloudSession.mockRejectedValue(
    Object.assign(new Error('Omi cloud session could not be refreshed'), {
      code: 'OMI_AUTH_TRANSPORT',
    }),
  );
  const renderer = await renderPage(ConnectorsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Apps unavailable');
  expect(tree).toContain(
    'Omi cloud at https://api.omi.me is unavailable. Check the connection, then retry.',
  );
  expect(tree).toContain('Retry');
  expect(tree).not.toContain('Loading apps…');
  expect(tree).not.toContain('Signed out');
  // Retry re-probes the session instead of stranding the loading spinner.
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockResolvedValue({id: 'apps', status: 200, body: '[]'});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Retry apps')
      .props.onPress();
  });
  expect(mockAuth.hasCloudSession).toHaveBeenCalledTimes(2);
});

test('a rejected session probe keeps settings retryable instead of loading forever', async () => {
  mockAuth.hasCloudSession.mockRejectedValue(
    Object.assign(new Error('Omi cloud session could not be refreshed'), {
      code: 'OMI_AUTH_TRANSPORT',
    }),
  );
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain(
    'Omi cloud at https://api.omi.me is unavailable. Check the connection, then retry.',
  );
  expect(labelsOf(renderer)).toContain('Retry settings');
  expect(tree).not.toContain('Loading account…');
});

test('a signed-out session still offers the native sign-in', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  const connectors = await renderPage(ConnectorsPage);
  expect(textOf(connectors)).toContain('Signed out');
  expect(textOf(connectors)).toContain(
    'Omi cloud needs a signed-in session.',
  );
  expect(labelsOf(connectors)).toContain('Sign in');
});
