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

const {RecordingTranscript} = require('./ui/RecordingTranscript');
const {parseRecordingTranscript} = require('./recordingTranscript');

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

test('shows pending state truthfully and reloads a completed result', async () => {
  mockRequest.mockResolvedValueOnce(response('session-one', 'queued'));
  const renderer = await render('session-one');
  expect(textOf(renderer)).toContain('Transcription is queued.');
  expect(textOf(renderer)).not.toContain('The transcript is empty.');
  mockRequest.mockResolvedValueOnce(
    response('session-one', 'completed', 'Persisted transcript'),
  );
  await act(async () =>
    renderer.root
      .findAll(
        node => node.props.accessibilityLabel === 'Reload recording transcript',
      )[0]!
      .props.onPress(),
  );
  expect(textOf(renderer)).toContain('Persisted transcript');
});

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
        <ConversationsPage outcome={outcome} loading={false} />,
      );
    });
    renderers.push(renderer);
    expect(mockRequest).not.toHaveBeenCalled();
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
