import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text} from 'react-native';
import type {NativeHttpResponse} from './omiNativeTypes';
import type {
  ConversationProjection,
  DomainReadOutcome,
} from './desktopReadClient';

const mockRequest = jest.fn();
let mockInvalidated: (() => void) | undefined;
jest.mock('./omiNative', () => ({
  omiBackend: {request: (request: unknown) => mockRequest(request)},
  subscribeOmiBackendSessionInvalidated: (listener: () => void) => {
    mockInvalidated = listener;
    return () => {
      mockInvalidated = undefined;
    };
  },
}));

const {
  deviceTranscriptionProjection,
} = require('../../backends/example-platform/apps/service/listen/device-transcription');
const {RecordingTranscript} = require('./ui/RecordingTranscript');
const {parseRecordingTranscript} = require('./recordingTranscriptContract');

function response(
  sessionId: string,
  state: string,
  text: string | null = null,
): NativeHttpResponse {
  return {
    id: 'test',
    status: 200,
    body: JSON.stringify({
      transcription: {
        sessionId,
        state,
        text,
        segments: [],
        language: null,
        errorCode: null,
        updatedAt: 123,
        discardedLeadingPackets: 0,
      },
    }),
  };
}
function textOf(renderer: ReactTestRenderer.ReactTestRenderer) {
  return renderer.root
    .findAllByType(Text)
    .map(node => node.props.children)
    .flat()
    .join(' ');
}
const renderers: ReactTestRenderer.ReactTestRenderer[] = [];
async function render(sessionId: string) {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <RecordingTranscript sessionId={sessionId} revision="1" />,
    );
  });
  renderers.push(renderer);
  return renderer;
}
afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()));
  mockRequest.mockReset();
});

test('loads full recording text through native transport without truncating to overview', async () => {
  const full =
    'Actual recorded speech. '.repeat(30) + 'Final words beyond overview.';
  mockRequest.mockResolvedValue(response('session-one', 'completed', full));
  const renderer = await render('session-one');
  expect(mockRequest).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    path: '/v1/device-sessions/session-one/transcript',
  });
  expect(textOf(renderer)).toContain(full);
  const text = renderer.root
    .findAllByType(Text)
    .find(node => node.props.children === full);
  expect(text?.props.selectable).toBe(true);
});

test('a completed whitespace-only transcript says empty instead of a blank body', async () => {
  mockRequest.mockResolvedValue(response('session-one', 'completed', ' \t\n'));
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('The transcript is empty.');
  expect(textOf(renderer)).not.toMatch(/ \t\n/);
});

test('a completed NEXT LINE-only transcript says empty instead of a blank body', async () => {
  mockRequest.mockResolvedValue(response('session-one', 'completed', '\u0085'));
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('The transcript is empty.');
  expect(textOf(renderer)).not.toContain('\u0085');
});

test('a completed NEXT LINE-prefixed transcript keeps later speech', async () => {
  mockRequest.mockResolvedValue(
    response('session-one', 'completed', '\u0085Recorded words'),
  );
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('Recorded words');
  expect(textOf(renderer)).not.toContain('\u0085');
  expect(textOf(renderer)).not.toContain('The transcript is empty.');
});

test.each(['queued', 'running'])(
  'shows %s state truthfully and resumes a completed result',
  async state => {
    mockRequest.mockResolvedValueOnce(response('session-one', state));
    const renderer = await render('session-one');
    expect(textOf(renderer)).toContain(
      state === 'queued'
        ? 'Transcription is queued.'
        : 'Transcription is in progress.',
    );
    expect(textOf(renderer)).not.toContain('The transcript is empty.');
    mockRequest.mockResolvedValueOnce(
      response('session-one', 'completed', 'Persisted transcript'),
    );
    await act(async () =>
      renderer.root
        .findAll(
          node =>
            node.props.accessibilityLabel === 'Reload recording transcript',
        )[0]!
        .props.onPress(),
    );
    expect(textOf(renderer)).toContain('Persisted transcript');
    expect(mockRequest).toHaveBeenLastCalledWith({
      id: expect.any(String),
      method: 'POST',
      path: '/v1/device-sessions/session-one/transcribe',
    });
  },
);

test('keeps failed processing and failed reads distinct without showing internal errors', async () => {
  mockRequest.mockResolvedValue(response('session-one', 'failed'));
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain(
    'This recording could not be transcribed.',
  );
  mockRequest.mockRejectedValue(new Error('private upstream details'));
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Reload recording transcript',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Transcript could not be loaded.');
  expect(textOf(renderer)).not.toContain('private upstream details');
});

test('a pending resume remains truthful without polling and a new recording starts with a read', async () => {
  mockRequest.mockResolvedValueOnce(response('session-one', 'queued'));
  const renderer = await render('session-one');
  mockRequest.mockResolvedValueOnce({
    ...response('session-one', 'running'),
    status: 202,
  });
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Reload recording transcript',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Transcription is in progress.');
  expect(mockRequest).toHaveBeenCalledTimes(2);
  mockRequest.mockResolvedValueOnce(
    response('session-two', 'completed', 'Current recording'),
  );
  await act(async () =>
    renderer.update(
      <RecordingTranscript sessionId="session-two" revision="1" />,
    ),
  );
  expect(mockRequest).toHaveBeenLastCalledWith({
    id: expect.any(String),
    method: 'GET',
    path: '/v1/device-sessions/session-two/transcript',
  });
});

test('retires a delayed read when the selected recording changes', async () => {
  let finish!: (value: NativeHttpResponse) => void;
  mockRequest.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('Loading transcript…');
  mockRequest.mockResolvedValueOnce(
    response('session-two', 'completed', 'Current transcript'),
  );
  await act(async () =>
    renderer.update(
      <RecordingTranscript sessionId="session-two" revision="1" />,
    ),
  );
  await act(async () =>
    finish(response('session-one', 'completed', 'Retired account text')),
  );
  expect(textOf(renderer)).toContain('Current transcript');
  expect(textOf(renderer)).not.toContain('Retired account text');
});

test('clears loaded text and rejects late completion after session invalidation', async () => {
  mockRequest.mockResolvedValueOnce(
    response('session-one', 'completed', 'Private transcript'),
  );
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('Private transcript');
  act(() => mockInvalidated?.());
  expect(textOf(renderer)).not.toContain('Private transcript');
  let finish!: (value: NativeHttpResponse) => void;
  mockRequest.mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Reload recording transcript',
      )[0]!
      .props.onPress(),
  );
  act(() => mockInvalidated?.());
  await act(async () =>
    finish(response('session-one', 'completed', 'Retired late text')),
  );
  expect(textOf(renderer)).not.toContain('Retired late text');
});

test('rejects another session, unknown states and malformed completion', () => {
  expect(
    parseRecordingTranscript(
      response('other', 'completed', 'wrong').body,
      'session-one',
    ),
  ).toBeNull();
  expect(
    parseRecordingTranscript(
      response('session-one', 'invented', 'wrong').body,
      'session-one',
    ),
  ).toBeNull();
  expect(
    parseRecordingTranscript(
      response('session-one', 'completed', null).body,
      'session-one',
    ),
  ).toBeNull();
  expect(
    parseRecordingTranscript('{"transcription":null}', 'session-one'),
  ).toBeNull();
});

test('opens a recording row into the full transcript detail and retires it on back', async () => {
  const {ConversationsPage} = require('./pages/Conversations');
  const native = require('react-native');
  const dimensions = jest
    .spyOn(native, 'useWindowDimensions')
    .mockReturnValue({width: 390, height: 844, scale: 1, fontScale: 1});
  const item: ConversationProjection = {
    kind: 'conversation',
    id: 'recording:session-one',
    title: 'Recorded conversation',
    summary: 'Short overview',
    searchableText: 'Short overview',
    createdAt: '2026-09-06T00:00:00Z',
    updatedAt: '2026-09-06T00:01:00Z',
    startedAt: null,
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const outcome: DomainReadOutcome<ConversationProjection> = {
    status: 'success',
    value: {
      items: [item],
      page: {
        windowStatus: 'complete',
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete',
        reasons: [],
      },
    },
  };
  mockRequest.mockResolvedValue(
    response(
      'session-one',
      'completed',
      'Actual full transcript beyond the summary',
    ),
  );
  try {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <ConversationsPage outcome={outcome} loading={false} embedded />,
      );
    });
    renderers.push(renderer);
    expect(mockRequest).not.toHaveBeenCalled();
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      ).length,
    ).toBeGreaterThan(0);
    await act(async () =>
      renderer.root
        .findAll(
          node =>
            node.props.accessibilityLabel ===
            'Open conversation Recorded conversation',
        )[0]!
        .props.onPress(),
    );
    expect(textOf(renderer)).toContain(
      'Actual full transcript beyond the summary',
    );
    expect(textOf(renderer)).not.toContain('Captured (device time)');
    expect(textOf(renderer)).not.toContain('Unlocked record');
    expect(textOf(renderer)).not.toContain('Active record');
    expect(textOf(renderer)).not.toContain('Locked');
    expect(textOf(renderer)).not.toContain('Discarded');
    await act(async () => {
      renderer.update(
        <ConversationsPage
          outcome={{
            ...outcome,
            value: {
              ...outcome.value,
              items: [
                {...item, locked: true, discarded: true, capturedAtMs: 0},
              ],
            },
          }}
          loading={false}
          embedded
        />,
      );
    });
    expect(textOf(renderer)).toContain('Captured (device time)');
    expect(textOf(renderer)).toContain('Time unavailable');
    expect(textOf(renderer)).not.toContain('1970');
    expect(textOf(renderer)).toContain('Started ·');
    expect(textOf(renderer)).toContain('Finished ·');
    expect(textOf(renderer)).toContain('Locked');
    expect(textOf(renderer)).toContain('Discarded');
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Search loaded conversations',
      ),
    ).toHaveLength(0);
    expect(
      renderer.root.findAll(
        node =>
          node.props.accessibilityLabel ===
          'Open conversation Recorded conversation',
      ),
    ).toHaveLength(0);
    await act(async () =>
      renderer.root
        .findAll(
          node => node.props.accessibilityLabel === 'Back to conversations',
        )[0]!
        .props.onPress(),
    );
    expect(textOf(renderer)).not.toContain(
      'Actual full transcript beyond the summary',
    );
    expect(textOf(renderer)).toContain('Short overview');
  } finally {
    dimensions.mockRestore();
  }
});

test('conversation list exposes refresh and load more with truthful pending actions', async () => {
  const {ConversationsPage} = require('./pages/Conversations');
  const onRefresh = jest.fn(),
    onLoadMore = jest.fn();
  const outcome = {
    status: 'success',
    value: {
      items: [],
      page: {
        windowStatus: 'more',
        complete: false,
        hasMore: true,
        nextCursor: 'next',
        completenessStatus: 'complete',
        reasons: [],
      },
    },
  };
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <ConversationsPage
        outcome={outcome}
        loading={false}
        onRefresh={onRefresh}
        onLoadMore={onLoadMore}
      />,
    );
  });
  renderers.push(renderer);
  const button = (name: string) =>
    renderer.root.findAll(node => node.props.accessibilityLabel === name)[0]!;
  act(() => {
    button('Refresh conversations').props.onPress();
    button('Load more conversations').props.onPress();
  });
  expect(onRefresh).toHaveBeenCalledTimes(1);
  expect(onLoadMore).toHaveBeenCalledTimes(1);
  expect(textOf(renderer)).toContain('Load more conversations');
  await act(async () => {
    renderer.update(
      <ConversationsPage
        outcome={outcome}
        loading={false}
        loadingMore
        onRefresh={onRefresh}
        onLoadMore={onLoadMore}
        notice="Conversations changed. The list has been refreshed."
      />,
    );
  });
  expect(button('Refresh conversations').props.disabled).toBe(true);
  expect(button('Load more conversations').props.disabled).toBe(true);
  expect(textOf(renderer)).toContain('The list has been refreshed');
});

test('a failed historical transcript read retries GET without requiring capture mutation authority', async () => {
  mockRequest.mockResolvedValueOnce({id: 'read', status: 503, body: null});
  const renderer = await render('historical-session');
  expect(textOf(renderer)).toContain('Transcript could not be loaded.');
  mockRequest.mockImplementationOnce(async (request: {method: string}) =>
    request.method === 'GET'
      ? response('historical-session', 'completed', 'Historical transcript')
      : {id: 'mutation', status: 409, body: null},
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Reload recording transcript',
      )[0]!
      .props.onPress(),
  );
  expect(mockRequest).toHaveBeenLastCalledWith({
    id: expect.any(String),
    method: 'GET',
    path: '/v1/device-sessions/historical-session/transcript',
  });
  expect(textOf(renderer)).toContain('Historical transcript');
});

test('nested non-retryable transcript 503s do not offer Check again', async () => {
  mockRequest.mockResolvedValueOnce({
    id: 'read',
    status: 503,
    body: JSON.stringify({
      error: {
        code: 'development_backend_unsupported',
        retryable: false,
        action: 'none',
      },
    }),
  });
  const renderer = await render('blocked-session');
  expect(textOf(renderer)).toContain(
    'Transcript is not available from this backend yet.',
  );
  expect(textOf(renderer)).not.toContain('Transcript could not be loaded.');
  expect(textOf(renderer)).not.toContain('Check again');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload recording transcript',
    ),
  ).toHaveLength(0);
});

test('native unsupported transcript throws do not offer Check again', async () => {
  mockRequest.mockRejectedValue({code: 'OMI_DEV_BACKEND_UNSUPPORTED'});
  const renderer = await render('unsupported-session');
  expect(textOf(renderer)).toContain(
    'Transcript is not available from this backend yet.',
  );
  expect(textOf(renderer)).not.toContain('Transcript could not be loaded.');
  expect(textOf(renderer)).not.toContain('Check again');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Reload recording transcript',
    ),
  ).toHaveLength(0);
});

test('thrown nested non-retryable transcript failures do not offer Check again', async () => {
  mockRequest.mockRejectedValue(
    Object.assign(new Error('unsupported'), {retryable: false}),
  );
  const renderer = await render('nested-throw-session');
  expect(textOf(renderer)).toContain(
    'Transcript is not available from this backend yet.',
  );
  expect(textOf(renderer)).not.toContain('Check again');
});

test.each([
  'attempt_limit',
  'invalid_audio',
  'private unknown upstream detail',
])(
  'terminal backend failure %s remains a read-only refresh',
  async errorCode => {
    const transcription = deviceTranscriptionProjection({
      sessionId: 'session-one',
      state: 'failed',
      providerResult: null,
      discardedLeadingPackets: 0,
      errorCode,
      updatedAt: 123,
      startedAt: '2026-09-07T00:00:00Z',
      codec: 21,
      chunkCount: 1,
      byteCount: 3,
    });
    const body = JSON.stringify({transcription});
    expect(parseRecordingTranscript(body, 'session-one')?.errorCode).toBe(
      errorCode,
    );
    mockRequest.mockResolvedValue({id: 'terminal', status: 200, body});
    const renderer = await render('session-one');
    expect(textOf(renderer)).toContain('cannot be retried');
    expect(textOf(renderer)).not.toContain('private unknown upstream detail');
    mockRequest.mockImplementation(async request =>
      request.method === 'GET'
        ? {id: 'terminal', status: 200, body}
        : {id: 'denied', status: 409, body: null},
    );
    await act(async () =>
      renderer.root
        .findAll(
          node =>
            node.props.accessibilityLabel === 'Reload recording transcript',
        )[0]!
        .props.onPress(),
    );
    expect(mockRequest).toHaveBeenLastCalledWith({
      id: expect.any(String),
      method: 'GET',
      path: '/v1/device-sessions/session-one/transcript',
    });
    expect(textOf(renderer)).toContain('cannot be retried');
    expect(textOf(renderer)).not.toContain('Transcript could not be loaded.');
  },
);
