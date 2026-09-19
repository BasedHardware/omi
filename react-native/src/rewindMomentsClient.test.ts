import {loadRewindMoments, upsertRewindMoment} from './rewindMomentsClient';
import type {OmiBackend} from './omiNativeTypes';

function backend(
  handler: (
    path: string,
    method: string,
    body?: string,
  ) => {
    status: number;
    body: string | null;
  },
): OmiBackend {
  return {
    request: async request => {
      const response = handler(request.path, request.method, request.body);
      return {
        id: request.id,
        status: response.status,
        body: response.body,
      };
    },
    generationEvents: async () => ({id: 'x', status: 404, body: null}),
    cancelGenerationEvents: async () => undefined,
  };
}

test('upserts metadata only and refuses invented pixels on read', async () => {
  const written: string[] = [];
  const adapter = backend((path, method, body) => {
    written.push(`${method} ${path} ${body ?? ''}`);
    if (method === 'POST') {
      return {
        status: 201,
        body: JSON.stringify({
          moment: {
            frameId: 'captured:owner:1',
            capturedAtMs: 10,
            appName: 'Notes',
            windowTitle: '',
            source: 'captured',
            ocrPreview: '',
          },
        }),
      };
    }
    return {
      status: 200,
      body: JSON.stringify({
        items: [
          {
            frameId: 'captured:owner:1',
            capturedAtMs: 10,
            appName: 'Notes',
            windowTitle: '',
            source: 'captured',
            ocrPreview: '',
            jpegBase64: 'nope',
          },
        ],
        window: {hasMore: false, nextCursor: null, complete: true},
      }),
    };
  });
  await upsertRewindMoment(adapter, {
    frameId: 'captured:owner:1',
    capturedAtMs: 10,
    appName: 'Notes',
    windowTitle: '',
    source: 'captured',
    ocrPreview: '',
  });
  expect(written[0]).toContain('/v1/rewind-moments');
  expect(written[0]).not.toContain('jpeg');
  await expect(loadRewindMoments(adapter)).rejects.toThrow(/pixel/);
});

test('failed writes stay failed instead of looking saved', async () => {
  const adapter = backend(() => ({
    status: 503,
    body: JSON.stringify({
      error: {code: 'service_unavailable', retryable: true, action: 'retry'},
    }),
  }));
  await expect(
    upsertRewindMoment(adapter, {
      frameId: 'captured:owner:1',
      capturedAtMs: 10,
      appName: 'Notes',
      windowTitle: '',
      source: 'captured',
      ocrPreview: '',
    }),
  ).rejects.toMatchObject({status: 503, backendCode: 'service_unavailable'});
});

test('a successful HTTP response must acknowledge the exact metadata', async () => {
  const moment = {
    frameId: 'captured:owner:1',
    capturedAtMs: 10,
    appName: 'Notes',
    windowTitle: 'Private',
    source: 'captured' as const,
    ocrPreview: '',
  };
  const adapter = backend(() => ({
    status: 201,
    body: JSON.stringify({moment: {...moment, frameId: 'captured:owner:2'}}),
  }));
  await expect(upsertRewindMoment(adapter, moment)).rejects.toThrow(
    /acknowledgement/,
  );
});

test.each([
  {hasMore: true, nextCursor: null},
  {hasMore: true, nextCursor: 'same-cursor'},
  {hasMore: false, nextCursor: 'unexpected'},
])('rejects invalid or non-advancing Recall pagination %j', async window => {
  const adapter = backend(() => ({
    status: 200,
    body: JSON.stringify({items: [], window}),
  }));
  await expect(loadRewindMoments(adapter, 'same-cursor')).rejects.toThrow(
    /pagination/,
  );
});
