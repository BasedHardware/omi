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
  getApiContract: jest.fn(),
  sendOmiChat: jest.fn(),
  cancelOmiChat: jest.fn(async (_id: string) => undefined),
  request: jest.fn(async (_value: {id: string}) => ({
    id: 'probe',
    status: 501,
    body: null as string | null,
  })),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(async () => undefined),
};

const mockNative = {
  getSnapshot: jest.fn(async () => ({
    bluetooth: 'unknown',
    devices: [],
    connectedDeviceId: null,
    phase: 'disconnected',
    capture: 'idle',
    lastEvent: null,
    microphone: 'unknown',
    notifications: 'unknown',
  })),
  startScan: jest.fn(async () => []),
};
const mockScanPermission = jest.fn(async () => true);

type TestMessage = {
  id: string;
  text: string;
  sender: 'human' | 'ai';
  createdAt: number;
  generationOutcome: 'completed' | 'cancelled' | null;
};

const capabilities = {
  maxAttachmentsPerMessage: 4,
  maxAttachmentBytes: 52_428_800,
  allowedAttachmentMimeTypes: ['text/plain'],
};

function wireMessage(message: TestMessage) {
  return {
    ...message,
    type: 'text',
    updatedAt: message.createdAt,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: 'sha256:test',
    messageSource: 'desktop_chat',
    rating: null,
    reported: false,
    revision: '1',
    attachments: [],
  };
}

function historyBody(
  messages: TestMessage[],
  page: {olderCursor: string | null; hasOlder: boolean} = {
    olderCursor: null,
    hasOlder: false,
  },
) {
  return JSON.stringify({
    messages: messages.map(wireMessage),
    page,
    capabilities,
  });
}

function admissionBody(message: TestMessage, generationId: string) {
  return JSON.stringify({
    message: wireMessage(message),
    generation: {id: generationId},
  });
}

jest.mock('../src/omiNative', () => ({
  omiAuth: mockAuth,
  omiBackend: mockBackend,
  omiNative: mockNative,
  isNativeModuleInstalled: true,
  isBluetoothScanAvailable: () => true,
  requestBluetoothScanPermission: mockScanPermission,
  browserScanErrorMessage: () => null,
  isNativeBackendInstalled: true,
  subscribeOmiBackendSessionInvalidated: () => () => undefined,
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

async function openSignIn(renderer: ReactTestRenderer.ReactTestRenderer) {
  for (const label of ['Get started', 'Continue']) {
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === label)
        .props.onPress(),
    );
  }
}
async function openChat(renderer: ReactTestRenderer.ReactTestRenderer) {
  if (labelsOf(renderer).includes('Chat with Omi')) {
    return;
  }
  await act(async () =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
}
async function reachAgreement(renderer: ReactTestRenderer.ReactTestRenderer) {
  for (const label of ['Continue without more permissions', 'Continue']) {
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === label)
        .props.onPress(),
    );
  }
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
  mockBackend.getApiContract.mockReset();
  mockBackend.sendOmiChat.mockReset();
  mockBackend.cancelOmiChat.mockClear();
  mockNative.getSnapshot.mockClear();
  mockNative.startScan.mockClear();
  mockScanPermission.mockClear();
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
  await openSignIn(renderer);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  expect(mockAuth.signIn).toHaveBeenCalledTimes(1);
  expect(mockAuth.markOnboardingComplete).not.toHaveBeenCalled();
  expect(textOf(renderer)).toContain('Choose what Omi can access');
  expect(mockBackend.request).not.toHaveBeenCalled();
  mockAuth.hasCloudSession.mockResolvedValue(true);
  await reachAgreement(renderer);
  await act(async () => {
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Agree and continue',
      )[0]
      .props.onPress();
  });
  expect(mockAuth.markOnboardingComplete).toHaveBeenCalledTimes(1);
  labels = labelsOf(renderer);
  expect(labels).not.toContain('First-run onboarding');
  expect(labels).toContain('Omi desktop chrome');
  expect(labels).toContain('Home currents');
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain('Ask about your day…');

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
  await openSignIn(renderer);
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
  expect(mockNative.getSnapshot).not.toHaveBeenCalled();
  expect(mockNative.startScan).not.toHaveBeenCalled();
  expect(mockScanPermission).not.toHaveBeenCalled();
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
              body: historyBody([]),
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
    body: `event: done\nid: terminal\ndata: ${JSON.stringify({
      kind: 'done',
      message: wireMessage({
        id: 'dead-session-reply',
        text: 'PRIVATE REPLY FROM THE DEAD SESSION',
        sender: 'ai',
        createdAt: 2,
        generationOutcome: 'completed',
      }),
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
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibar.props.onChangeText('PRIVATE IN-FLIGHT MESSAGE');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
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
      body: admissionBody(
        {
          id: 'dead-session-human',
          text: 'PRIVATE IN-FLIGHT MESSAGE',
          sender: 'human',
          createdAt: 1,
          generationOutcome: null,
        },
        'gen-1',
      ),
    });
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('First-run onboarding');

  // The next account signs in and its history load fails: nothing from the
  // previous account may render in its shell.
  nextSession = true;
  await openSignIn(renderer);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(labelsOf(renderer)).toContain('Omi desktop chrome');
  await openChat(renderer);
  expect(textOf(renderer)).not.toContain('PRIVATE IN-FLIGHT MESSAGE');
  expect(textOf(renderer)).not.toContain('PRIVATE REPLY FROM THE DEAD SESSION');
  expect(labelsOf(renderer)).toContain('Send');

  // The retired send did not brick the composer: a fresh message still
  // starts a new admission.
  const omnibarAgain = renderer.root
    .findAllByType(TextInput)
    .find(
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibarAgain.props.onChangeText('fresh account message');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
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
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockAuth.signIn.mockResolvedValue({signedIn: true});
  mockAuth.signOut.mockResolvedValue({signedOut: true});
  mockBackend.request.mockImplementation(async (value: {id: string}) => {
    if (value.id === 'chat-history') {
      return {
        id: 'chat-history',
        status: 200,
        body: historyBody([
          {
            id: 'prior-session-message',
            text: 'PRIVATE PRIOR SESSION',
            sender: 'human',
            createdAt: 1,
            generationOutcome: null,
          },
        ]),
      };
    }
    return {id: value.id, status: 501, body: null};
  });

  const renderer = await renderApp();
  await openSignIn(renderer);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  await act(async () => {
    await Promise.resolve();
  });
  await openChat(renderer);
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
  await openSignIn(renderer);
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
  await openChat(renderer);
  expect(textOf(renderer)).not.toContain('PRIVATE PRIOR SESSION');
});

test('a stale older-history recovery cannot overwrite a newer desktop send', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  let historyCall = 0;
  let resolveStaleRecovery:
    | ((value: {id: string; status: number; body: string}) => void)
    | undefined;
  const canonicalMessages: TestMessage[] = [
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
            body: historyBody([], {
              olderCursor: 'older-1',
              hasOlder: true,
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
          body: historyBody(canonicalMessages),
        });
      }
      if (value.id.startsWith('admit-')) {
        return Promise.resolve({
          id: value.id,
          status: 201,
          body: admissionBody(canonicalMessages[0], 'fresh-generation'),
        });
      }
      return Promise.resolve({id: value.id, status: 501, body: null});
    },
  );
  mockBackend.generationEvents.mockResolvedValue({
    id: 'fresh-generation',
    status: 200,
    body: `event: done\nid: terminal\ndata: ${JSON.stringify({
      kind: 'done',
      message: wireMessage(canonicalMessages[1]),
    })}\n\n`,
  });

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  await openChat(renderer);
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
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibar.props.onChangeText('fresh question');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('fresh answer');

  await act(async () => {
    resolveStaleRecovery!({
      id: 'chat-history',
      status: 200,
      body: historyBody([]),
    });
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('fresh question');
  expect(textOf(renderer)).toContain('fresh answer');
});

test.each(['', 'next question'])(
  'a rejected admission preserves the draft when the next draft is %j',
  async nextDraft => {
    mockBackend.generationEvents.mockClear();
    mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
    mockAuth.hasCloudSession.mockResolvedValue(true);
    let rejectAdmission: ((error: Error) => void) | undefined;
    mockBackend.request.mockImplementation(async (value: {id: string}) => {
      if (value.id === 'chat-history') {
        return {id: value.id, status: 200, body: historyBody([])};
      }
      if (value.id.startsWith('admit-')) {
        return new Promise((_resolve, reject) => {
          rejectAdmission = reject;
        });
      }
      return {id: value.id, status: 501, body: null};
    });
    const renderer = await renderApp();
    const omnibar = renderer.root
      .findAllByType(TextInput)
      .find(
        node =>
          node.props.placeholder === 'Ask about your day…' ||
          node.props.placeholder === 'Message Omi…',
      )!;
    act(() => {
      omnibar.props.onChangeText('unsent question');
    });
    await act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Send')
        .props.onPress();
      await flushAsyncQueue();
    });
    const composer = renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.onChangeText !== undefined)!;
    act(() => {
      composer.props.onChangeText(nextDraft);
    });
    await act(async () => {
      rejectAdmission!(new Error('offline'));
      await flushAsyncQueue();
    });
    expect(
      renderer.root
        .findAllByType(TextInput)
        .some(node => node.props.value === (nextDraft || 'unsent question')),
    ).toBe(true);
    expect(textOf(renderer)).toContain(
      'Message not sent. Check your connection and try again.',
    );
    expect(mockBackend.generationEvents).not.toHaveBeenCalled();
  },
);

test('an admitted stream failure keeps its uncertain interruption visible', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(
    async (value: {id: string; body?: string}) => {
      if (value.id === 'chat-history') {
        return {id: value.id, status: 200, body: historyBody([])};
      }
      if (value.id.startsWith('admit-')) {
        const body = JSON.parse(value.body ?? '{}') as {
          id: string;
          text: string;
          at: number;
        };
        return {
          id: value.id,
          status: 201,
          body: admissionBody(
            {
              id: body.id,
              text: body.text,
              sender: 'human',
              createdAt: body.at,
              generationOutcome: null,
            },
            'generation-interrupted',
          ),
        };
      }
      return {id: value.id, status: 501, body: null};
    },
  );
  mockBackend.generationEvents.mockRejectedValue(
    Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'}),
  );

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibar.props.onChangeText('interrupted question');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
    await flushAsyncQueue();
  });

  expect(textOf(renderer)).toContain('interrupted question');
  expect(textOf(renderer)).toContain(
    'Response interrupted. It may still complete.',
  );
  await act(async () => {
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain(
    'Response interrupted. It may still complete.',
  );
});

test('a send during the initial history load still receives the transcript', async () => {
  // send() bumps chatMutationSeqRef so an in-flight setMessages(page) cannot
  // wipe the optimistic row. The same bump used to discard the history page
  // entirely, leaving olderCursor null with no recovery. History must merge.
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const historyResolvers: Array<
    (value: {id: string; status: number; body: string | null}) => void
  > = [];
  mockBackend.request.mockImplementation(
    async (value: {id: string; body?: string}) => {
      if (value.id === 'chat-history') {
        return new Promise(resolve => {
          historyResolvers.push(resolve);
        });
      }
      if (value.id.startsWith('admit-')) {
        const body = JSON.parse(value.body ?? '{}') as {
          id: string;
          text: string;
          at: number;
        };
        return {
          id: value.id,
          status: 201,
          body: admissionBody(
            {
              id: body.id,
              text: body.text,
              sender: 'human',
              createdAt: body.at,
              generationOutcome: null,
            },
            'gen-during-history',
          ),
        };
      }
      return {id: value.id, status: 501, body: null};
    },
  );
  mockBackend.generationEvents.mockResolvedValue({
    id: 'gen-during-history',
    status: 200,
    body: `event: done\nid: terminal\ndata: ${JSON.stringify({
      kind: 'done',
      message: wireMessage({
        id: 'gen-during-history',
        text: 'reply while history pending',
        sender: 'ai',
        createdAt: 20,
        generationOutcome: 'completed',
      }),
    })}\n\n`,
  });

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  expect(historyResolvers.length).toBeGreaterThan(0);

  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibar.props.onChangeText('sent before history landed');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('sent before history landed');
  expect(textOf(renderer)).toContain('reply while history pending');

  const historyPage = historyBody(
    [
      {
        id: 'prior-1',
        text: 'PRIOR HISTORY MESSAGE',
        sender: 'human',
        createdAt: 1,
        generationOutcome: null,
      },
      {
        id: 'prior-2',
        text: 'PRIOR HISTORY REPLY',
        sender: 'ai',
        createdAt: 2,
        generationOutcome: 'completed',
      },
    ],
    {olderCursor: 'older-from-initial', hasOlder: true},
  );
  await act(async () => {
    // Strict Mode may have started more than one load; settle every waiter.
    historyResolvers.splice(0).forEach(resolve => {
      resolve({
        id: 'chat-history',
        status: 200,
        body: historyPage,
      });
    });
    await flushAsyncQueue();
  });

  expect(textOf(renderer)).toContain('PRIOR HISTORY MESSAGE');
  expect(textOf(renderer)).toContain('PRIOR HISTORY REPLY');
  expect(textOf(renderer)).toContain('sent before history landed');
  expect(textOf(renderer)).toContain('reply while history pending');
  expect(labelsOf(renderer)).toContain('Load earlier messages');
});

test('a send during an older-history load still keeps the earlier page', async () => {
  // send() bumps chatMutationSeqRef. That used to discard a successfully
  // fetched older page entirely — losing those messages and leaving the same
  // olderCursor with no applied progress. Merge the page; only a session epoch
  // change retires it. 410 recovery stays mutation-fenced separately.
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);

  const olderResolvers: Array<
    (value: {id: string; status: number; body: string | null}) => void
  > = [];
  mockBackend.request.mockImplementation(
    async (value: {id: string; body?: string; path?: string}) => {
      if (value.id === 'chat-history') {
        if (value.path != null && value.path.includes('olderCursor=')) {
          return new Promise(resolve => {
            olderResolvers.push(resolve);
          });
        }
        return {
          id: value.id,
          status: 200,
          body: historyBody(
            [
              {
                id: 'recent-1',
                text: 'RECENT HISTORY',
                sender: 'human',
                createdAt: 10,
                generationOutcome: null,
              },
            ],
            {olderCursor: 'older-pending', hasOlder: true},
          ),
        };
      }
      if (value.id.startsWith('admit-')) {
        const body = JSON.parse(value.body ?? '{}') as {
          id: string;
          text: string;
          at: number;
        };
        return {
          id: value.id,
          status: 201,
          body: admissionBody(
            {
              id: body.id,
              text: body.text,
              sender: 'human',
              createdAt: body.at,
              generationOutcome: null,
            },
            'gen-during-older',
          ),
        };
      }
      return {id: value.id, status: 501, body: null};
    },
  );
  mockBackend.generationEvents.mockResolvedValue({
    id: 'gen-during-older',
    status: 200,
    body: `event: done\nid: terminal\ndata: ${JSON.stringify({
      kind: 'done',
      message: wireMessage({
        id: 'gen-during-older',
        text: 'reply while older pending',
        sender: 'ai',
        createdAt: 30,
        generationOutcome: 'completed',
      }),
    })}\n\n`,
  });

  const renderer = await renderApp();
  await act(async () => {
    await flushAsyncQueue();
  });
  await openChat(renderer);
  expect(textOf(renderer)).toContain('RECENT HISTORY');
  expect(labelsOf(renderer)).toContain('Load earlier messages');

  await openChat(renderer);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load earlier messages')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(olderResolvers.length).toBeGreaterThan(0);

  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node =>
        node.props.placeholder === 'Ask about your day…' ||
        node.props.placeholder === 'Message Omi…',
    )!;
  act(() => {
    omnibar.props.onChangeText('sent while older loading');
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
    await flushAsyncQueue();
  });
  expect(textOf(renderer)).toContain('sent while older loading');
  expect(textOf(renderer)).toContain('reply while older pending');

  const olderPage = historyBody(
    [
      {
        id: 'older-1',
        text: 'OLDER HISTORY MESSAGE',
        sender: 'human',
        createdAt: 1,
        generationOutcome: null,
      },
      {
        id: 'older-2',
        text: 'OLDER HISTORY REPLY',
        sender: 'ai',
        createdAt: 2,
        generationOutcome: 'completed',
      },
    ],
    {olderCursor: 'older-next', hasOlder: true},
  );
  await act(async () => {
    olderResolvers.splice(0).forEach(resolve => {
      resolve({
        id: 'chat-history',
        status: 200,
        body: olderPage,
      });
    });
    await flushAsyncQueue();
  });

  expect(textOf(renderer)).toContain('OLDER HISTORY MESSAGE');
  expect(textOf(renderer)).toContain('OLDER HISTORY REPLY');
  await openChat(renderer);
  expect(textOf(renderer)).toContain('RECENT HISTORY');
  expect(textOf(renderer)).toContain('sent while older loading');
  expect(textOf(renderer)).toContain('reply while older pending');
  expect(labelsOf(renderer)).toContain('Load earlier messages');
});

test('signed-in macOS Settings exposes device scanning only after an explicit action', async () => {
  mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
  mockAuth.hasCloudSession.mockResolvedValue(true);
  const renderer = await renderApp();
  expect(mockNative.getSnapshot).toHaveBeenCalled();
  expect(mockNative.startScan).not.toHaveBeenCalled();
  expect(mockScanPermission).not.toHaveBeenCalled();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
  });
  expect(textOf(renderer)).toContain('Devices');
  expect(mockNative.startScan).not.toHaveBeenCalled();
  expect(mockScanPermission).not.toHaveBeenCalled();
  await act(async () => {
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Scan for Omi devices',
      )[0]
      .props.onPress();
  });
  expect(mockScanPermission).toHaveBeenCalledTimes(1);
  expect(mockNative.startScan).toHaveBeenCalledTimes(1);
  expect(mockNative.startScan).toHaveBeenCalledWith(8);
});

test.each(['stop', 'unmount', 'signout'])(
  'old chat %s cancels its request and fences late response',
  async mode => {
    mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
    mockAuth.hasCloudSession.mockResolvedValue(true);
    mockBackend.getApiContract.mockResolvedValue('omi');
    mockBackend.request.mockImplementation(async value => ({
      id: value.id,
      status: 200,
      body: '[]',
    }));
    let settle!: (value: {id: string; status: number; body: string}) => void;
    mockBackend.sendOmiChat.mockImplementation(
      () =>
        new Promise(resolve => {
          settle = resolve;
        }),
    );
    const renderer = await renderApp();
    await act(async () => {
      await flushAsyncQueue();
    });
    const omnibar = renderer.root
      .findAllByType(TextInput)
      .find(
        node =>
          node.props.placeholder === 'Ask about your day…' ||
          node.props.placeholder === 'Message Omi…',
      )!;
    act(() => omnibar.props.onChangeText('my old request'));
    await act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Send')
        .props.onPress();
    });
    expect(mockBackend.sendOmiChat).toHaveBeenCalledTimes(1);
    const requestId = mockBackend.sendOmiChat.mock.calls[0][0];
    expect(labelsOf(renderer)).toContain('Stop');
    if (mode === 'stop')
      await act(async () => {
        renderer.root
          .find(node => node.props.accessibilityLabel === 'Stop')
          .props.onPress();
      });
    else if (mode === 'signout') {
      mockAuth.hasCloudSession.mockResolvedValue(false);
      mockAuth.signOut.mockResolvedValue({signedOut: true});
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
    } else await act(async () => renderer.unmount());
    expect(mockBackend.cancelOmiChat).toHaveBeenCalledWith(requestId);
    await act(async () => {
      settle({
        id: requestId,
        status: 200,
        body: `done: ${Buffer.from(
          JSON.stringify({
            id: 'late-server',
            text: 'PRIVATE LATE RESPONSE',
            sender: 'ai',
            created_at: '2026-09-07T00:00:00Z',
          }),
        ).toString('base64')}\n\n`,
      });
    });
    if (mode === 'signout')
      expect(textOf(renderer)).not.toContain('PRIVATE LATE RESPONSE');
    if (mode === 'stop') {
      expect(textOf(renderer)).not.toContain('PRIVATE LATE RESPONSE');
      expect(textOf(renderer)).toContain('may still complete on the server');
    }
  },
);
