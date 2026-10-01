import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  loadLegacyConversationDetail,
  legacyConversationDetailErrorCopy,
} from './legacyConversationDetail';
import {useLegacyConversationDetail} from './useLegacyConversationDetail';
import type {NativeHttpResponse, OmiBackend} from './omiNativeTypes';

const mockRequest = jest.fn();
const mockContract = jest.fn();
let mockInvalidated: (() => void) | undefined;
jest.mock('./omiNative', () => ({
  omiBackend: {
    request: (request: unknown) => mockRequest(request),
    getApiContract: () => mockContract(),
  },
  subscribeOmiBackendSessionInvalidated: (callback: () => void) => {
    mockInvalidated = callback;
    return () => {
      mockInvalidated = undefined;
    };
  },
}));
const backend = {
  request: mockRequest,
  getApiContract: mockContract,
} as unknown as OmiBackend;
const fixture = {
  id: 'conversation/one',
  is_locked: false,
  structured: {
    title: 'A real conversation',
    overview: 'Summary',
    sections: [{heading: 'Notes', body_markdown: 'Full notes'}],
  },
  transcript_segments: [
    {
      text: 'Full speech beyond the summary',
      speaker: 'SPEAKER_00',
      is_user: true,
      start: 0.25,
      end: 4.5,
    },
  ],
};
function response(value: unknown = fixture, status = 200): NativeHttpResponse {
  return {id: 'detail', status, body: JSON.stringify(value)};
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => {
    resolve = done;
  });
  return {promise, resolve};
}
let state: ReturnType<typeof useLegacyConversationDetail>;
function Harness({id, revision}: {id: string | null; revision?: string}) {
  state = useLegacyConversationDetail(id, revision);
  return null;
}
let renderer: ReactTestRenderer.ReactTestRenderer | undefined;
async function mount(id: string | null = fixture.id) {
  await act(async () => {
    renderer = ReactTestRenderer.create(<Harness id={id} />);
  });
}
beforeEach(() => {
  mockContract.mockReset().mockResolvedValue('omi');
  mockRequest.mockReset().mockResolvedValue(response());
});
afterEach(async () => {
  await act(async () => renderer?.unmount());
  renderer = undefined;
});

test('uses the actual old detail wire and retains full notes and transcript', async () => {
  const value = await loadLegacyConversationDetail(backend, fixture.id);
  expect(mockRequest).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/conversations/conversation%2Fone',
  });
  expect(value.sections).toEqual([
    {heading: 'Notes', bodyMarkdown: 'Full notes'},
  ]);
  expect(value.transcript).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
});

test.each([undefined, null])(
  'omitted/null transcript stays unknown (%s)',
  async transcript_segments => {
    mockRequest.mockResolvedValue(response({...fixture, transcript_segments}));
    expect(
      (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
    ).toEqual({status: 'unavailable'});
  },
);

test('locked transcript is unavailable while explicit unlocked empty transcript is known', async () => {
  mockRequest.mockResolvedValueOnce(
    response({...fixture, is_locked: true, transcript_segments: []}),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript.status,
  ).toBe('unavailable');
  mockRequest.mockResolvedValueOnce(
    response({...fixture, transcript_segments: []}),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({status: 'loaded', segments: []});
});

test.each([
  {...fixture, id: 'another-conversation'},
  {...fixture, transcript_segments: 'compressed-or-malformed'},
  {
    ...fixture,
    transcript_segments: [{...fixture.transcript_segments[0], start: '0'}],
  },
  {
    ...fixture,
    transcript_segments: [{...fixture.transcript_segments[0], is_user: null}],
  },
  {
    ...fixture,
    transcript_segments: Array(20001).fill(fixture.transcript_segments[0]),
  },
  {
    ...fixture,
    structured: {
      ...fixture.structured,
      sections: [{heading: 'Notes', body_markdown: 5}],
    },
  },
])(
  'rejects mismatched or malformed detail without partial acknowledgement',
  async value => {
    mockRequest.mockResolvedValueOnce(response(value));
    await expect(
      loadLegacyConversationDetail(backend, fixture.id),
    ).rejects.toThrow();
  },
);

test('rejects oversized body and malformed JSON before publishing detail', async () => {
  for (const body of ['x'.repeat(6 * 1024 * 1024 + 1), '{']) {
    mockRequest.mockResolvedValueOnce({status: 200, body});
    await expect(
      loadLegacyConversationDetail(backend, fixture.id),
    ).rejects.toThrow();
  }
});

test.each([401, 403, 404, 500])(
  'HTTP %s is a fixed-copy failure without server text',
  async status => {
    mockRequest.mockResolvedValueOnce(
      response({error: 'private backend diagnostics'}, status),
    );
    const error = await loadLegacyConversationDetail(backend, fixture.id).catch(
      value => value,
    );
    const copy = legacyConversationDetailErrorCopy(error);
    expect(copy).not.toContain('private');
    expect(copy).toMatch(
      status === 401
        ? /Sign in/
        : status === 404
        ? /no longer available/
        : /could not be loaded/,
    );
  },
);

test('canonical and unknown selection never dispatch the old detail request', async () => {
  for (const contract of ['canonical', undefined]) {
    mockContract.mockResolvedValueOnce(contract);
    await expect(
      loadLegacyConversationDetail(backend, fixture.id),
    ).rejects.toThrow();
  }
  expect(mockRequest).not.toHaveBeenCalled();
});

test('late selection response cannot replace current detail; retry is GET', async () => {
  const old = deferred<NativeHttpResponse>();
  mockRequest.mockReturnValueOnce(old.promise);
  await mount();
  mockRequest.mockResolvedValue(response({...fixture, id: 'second'}));
  await act(async () => renderer!.update(<Harness id="second" />));
  await act(async () => old.resolve(response()));
  expect(state.result.status).toBe('loaded');
  expect(state.result.conversationId).toBe('second');
  await act(async () => state.reload());
  expect(
    mockRequest.mock.calls.every(([request]) => request.method === 'GET'),
  ).toBe(true);
  expect(mockRequest).toHaveBeenCalledTimes(3);
});

test('auth retirement during contract lookup prevents even dispatching a stale request', async () => {
  const contract = deferred<'omi'>();
  mockContract.mockReturnValueOnce(contract.promise);
  await mount();
  await act(async () => mockInvalidated?.());
  await act(async () => contract.resolve('omi'));
  expect(mockRequest).not.toHaveBeenCalled();
  expect(state.result.status).toBe('error');
});

test('auth retirement removes loaded text and fences pending detail publication', async () => {
  await mount();
  expect(state.result.status).toBe('loaded');
  const pending = deferred<NativeHttpResponse>();
  mockRequest.mockReturnValueOnce(pending.promise);
  await act(async () => state.reload());
  await act(async () => mockInvalidated?.());
  await act(async () => pending.resolve(response()));
  expect(state.result.status).toBe('error');
  expect(state.result).not.toHaveProperty('value');
});

test('unmount while contract lookup is pending prevents request dispatch', async () => {
  const contract = deferred<'omi'>();
  mockContract.mockReturnValueOnce(contract.promise);
  await mount();
  await act(async () => renderer!.unmount());
  renderer = undefined;
  await act(async () => contract.resolve('omi'));
  expect(mockRequest).not.toHaveBeenCalled();
  expect(mockInvalidated).toBeUndefined();
});
