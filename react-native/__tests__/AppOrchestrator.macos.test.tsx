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
  request: jest.fn(async (_value: {id: string}) => ({
    id: 'probe',
    status: 501,
    body: null as string | null,
  })),
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

async function flushAsyncQueue() {
  for (let index = 0; index < 10; index += 1) {
    await Promise.resolve();
  }
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

test('Welcome and the session probe keep the cloud network idle', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);

  const renderer = await renderApp();
  await act(async () => {
    await Promise.resolve();
  });
  // A probing or signed-out Mac never hits /v1/conversations|memories|tasks
  // or chat history: those 401/unconfigured failures must not poison the
  // phase for the session that signs in next.
  expect(labelsOf(renderer)).toContain('First-run onboarding');
  expect(mockBackend.request).not.toHaveBeenCalled();
});

test('a send still in flight when the session dies never seeds the next session', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true).mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});

  let nextSession = false;
  let resolveAdmission:
    | ((value: {id: string; status: number; body: string | null}) => void)
    | undefined;
  const readResolvers: Array<
    (value: {id: string; status: number; body: string | null}) => void
  > = [];
  mockBackend.request.mockImplementation((value: {id: string}) => {
    if (value.id === 'chat-history') {
      return Promise.resolve(
        nextSession
          ? {id: value.id, status: 501, body: null}
          : {
              id: value.id,
              status: 200,
              body: JSON.stringify({
                messages: [],
                page: {olderCursor: null, hasOlder: false},
              }),
            },
      );
    }
    if (value.id.startsWith('admit-')) {
      return new Promise(resolve => {
        resolveAdmission = resolve;
      });
    }
    if (value.id.startsWith('desktop-')) {
      return new Promise(resolve => {
        readResolvers.push(resolve);
      });
    }
    return Promise.resolve({id: value.id, status: 501, body: null});
  });
  mockBackend.generationEvents.mockImplementation(async () => ({
    id: 'gen-1',
    status: 200,
    body: `data: ${JSON.stringify({
      kind: 'done',
      message: {
        id: 'dead-session-reply',
        text: 'PRIVATE REPLY FROM THE DEAD SESSION',
        sender: 'ai',
        createdAt: 2,
        generationOutcome: 'completed',
      },
    })}\n\n`,
  }));

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('Omi desktop chrome');
  expect(readResolvers.length).toBe(3);

  // A send starts while the session is still ready.
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  act(() => {
    omnibar.props.onChangeText('PRIVATE IN-FLIGHT MESSAGE');
  });
  await act(async () => {
    omnibar.props.onSubmitEditing();
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('PRIVATE IN-FLIGHT MESSAGE');
  expect(resolveAdmission).toBeDefined();

  // The session dies mid-send: every read comes back 401 and the probe
  // confirms the keychain session is gone, so the gate falls to Welcome.
  await act(async () => {
    for (const resolve of readResolvers.splice(0)) {
      resolve({
        id: 'reads',
        status: 401,
        body: JSON.stringify({
          error: {
            code: 'unauthorized',
            retryable: false,
            action: 'reauthenticate',
          },
        }),
      });
    }
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('First-run onboarding');
  expect(textOf(renderer)).not.toContain('PRIVATE IN-FLIGHT MESSAGE');

  // The dead session's send settles only now: its canonical human and
  // assistant messages must not seed the transcript of any later session.
  await act(async () => {
    resolveAdmission!({
      id: 'admission',
      status: 200,
      body: JSON.stringify({
        message: {
          id: 'dead-session-human',
          text: 'PRIVATE IN-FLIGHT MESSAGE',
          sender: 'human',
          createdAt: 1,
          generationOutcome: null,
        },
        generation: {id: 'gen-1'},
      }),
    });
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('First-run onboarding');

  // The next account signs in and its history load fails: nothing from the
  // previous account may render in its shell.
  nextSession = true;
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('Omi desktop chrome');
  expect(textOf(renderer)).not.toContain('PRIVATE IN-FLIGHT MESSAGE');
  expect(textOf(renderer)).not.toContain('PRIVATE REPLY FROM THE DEAD SESSION');
  expect(labelsOf(renderer)).toContain('Send');

  // The retired send did not brick the composer: a fresh message still
  // starts a new admission.
  const omnibarAgain = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  act(() => {
    omnibarAgain.props.onChangeText('fresh account message');
  });
  await act(async () => {
    omnibarAgain.props.onSubmitEditing();
    await flushAsyncQueue();
  });
  expect(
    mockBackend.request.mock.calls.filter(([value]: [{id: string}]) =>
      value.id.startsWith('admit-'),
    ),
  ).toHaveLength(2);
});

test('a mid-run 401 leaves the product shell once the session is gone', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValueOnce(true).mockResolvedValue(false);
  mockBackend.request.mockImplementation(async () => ({
    id: 'unauthorized',
    status: 401,
    body: JSON.stringify({
      error: {code: 'unauthorized', retryable: false, action: 'reauthenticate'},
    }),
  }));

  const renderer = await renderApp();
  await act(async () => {
    await Promise.resolve();
  });
  // The keychain session died mid-run; every read and the history load came
  // back 401, so the gate re-probes and falls back to Welcome instead of
  // keeping nav, omnibar, and recovery banners up on dead credentials.
  expect(labelsOf(renderer)).not.toContain('Omi desktop chrome');
  expect(labelsOf(renderer)).toContain('First-run onboarding');
  expect(mockAuth.hasCloudSession).toHaveBeenCalledTimes(2);
});

test('the previous session transcript never survives a sign-out', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  mockBackend.request.mockImplementation(async (value: {id: string}) => {
    if (value.id === 'chat-history') {
      return {
        id: 'chat-history',
        status: 200,
        body: JSON.stringify({
          messages: [
            {
              id: 'prior-session-message',
              text: 'PRIVATE PRIOR SESSION',
              sender: 'human',
              createdAt: 1,
              generationOutcome: null,
            },
          ],
          page: {olderCursor: null, hasOlder: false},
        }),
      };
    }
    return {id: value.id, status: 501, body: null};
  });

  const renderer = await renderApp();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  await act(async () => {
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain('PRIVATE PRIOR SESSION');

  mockBackend.request.mockImplementation(async () => ({
    id: 'gone',
    status: 501,
    body: null,
  }));
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
  expect(labelsOf(renderer)).toContain('First-run onboarding');
  expect(textOf(renderer)).not.toContain('PRIVATE PRIOR SESSION');

  // The next sign-in starts from an empty transcript even when history
  // cannot load: the prior account's bubbles must never flash back in.
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  await act(async () => {
    await Promise.resolve();
  });
  expect(labelsOf(renderer)).toContain('Omi desktop chrome');
  expect(labelsOf(renderer)).toContain('Home currents');
  expect(textOf(renderer)).not.toContain('PRIVATE PRIOR SESSION');
});

test('a stale older-history recovery cannot overwrite a newer desktop send', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  let historyCall = 0;
  let resolveStaleRecovery:
    | ((value: {id: string; status: number; body: string}) => void)
    | undefined;
  const canonicalMessages = [
    {
      id: 'fresh-human',
      text: 'fresh question',
      sender: 'human',
      createdAt: 2,
      generationOutcome: null,
    },
    {
      id: 'fresh-ai',
      text: 'fresh answer',
      sender: 'ai',
      createdAt: 3,
      generationOutcome: 'completed',
    },
  ];
  mockBackend.request.mockImplementation(
    (value: {id: string; path?: string}) => {
      if (value.id === 'chat-history') {
        historyCall += 1;
        if (historyCall === 1) {
          return Promise.resolve({
            id: value.id,
            status: 200,
            body: JSON.stringify({
              messages: [],
              page: {olderCursor: 'older-1', hasOlder: true},
            }),
          });
        }
        if (historyCall === 2) {
          return Promise.resolve({
            id: value.id,
            status: 410,
            body: JSON.stringify({
              error: {
                code: 'cursor_expired',
                retryable: false,
                action: 'refresh_history',
              },
            }),
          });
        }
        if (historyCall === 3) {
          return new Promise(resolve => {
            resolveStaleRecovery = resolve;
          });
        }
        return Promise.resolve({
          id: value.id,
          status: 200,
          body: JSON.stringify({
            messages: canonicalMessages,
            page: {olderCursor: null, hasOlder: false},
          }),
        });
      }
      if (value.id.startsWith('admit-')) {
        return Promise.resolve({
          id: value.id,
          status: 201,
          body: JSON.stringify({
            message: canonicalMessages[0],
            generation: {id: 'fresh-generation'},
          }),
        });
      }
      return Promise.resolve({id: value.id, status: 501, body: null});
    },
  );
  mockBackend.generationEvents.mockResolvedValue({
    id: 'fresh-generation',
    status: 200,
    body: `data: ${JSON.stringify({
      kind: 'done',
      message: canonicalMessages[1],
    })}\n\n`,
  });

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load earlier messages')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(resolveStaleRecovery).toBeDefined();

  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  act(() => {
    omnibar.props.onChangeText('fresh question');
  });
  await act(async () => {
    omnibar.props.onSubmitEditing();
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('fresh answer');

  await act(async () => {
    resolveStaleRecovery!({
      id: 'chat-history',
      status: 200,
      body: JSON.stringify({
        messages: [],
        page: {olderCursor: null, hasOlder: false},
      }),
    });
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('fresh question');
  expect(textOf(renderer)).toContain('fresh answer');
});
