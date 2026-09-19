import {
  prepareTimelineMemory,
  saveTimelineMemory,
  sendTimelineMemory,
  STM_NOTES_OPS_PATH,
} from './memoryNoteClient';
import type {OmiBackend} from './omiNativeTypes';

function backend(response: {status: number; body: string | null}): OmiBackend {
  return {
    getApiContract: async () => 'canonical',
    createWriteId: async () => 'a'.repeat(64),
    request: async request => ({
      id: request.id,
      status: response.status,
      body: response.body,
    }),
    generationEvents: async () => ({id: 'generation', status: 404, body: null}),
    cancelGenerationEvents: async () => undefined,
  };
}

test('saves an explicit note through the authenticated STM-note door', async () => {
  const requests: string[] = [];
  const base = backend({
    status: 200,
    body: JSON.stringify({
      applied: {
        record_id: `timeline-${'a'.repeat(48)}`,
        revision: 'b'.repeat(64),
      },
      idempotent: false,
    }),
  });
  const result = await saveTimelineMemory(
    {
      ...base,
      request: async request => {
        requests.push(
          `${request.method} ${request.path} ${request.body ?? ''}`,
        );
        return base.request(request);
      },
    },
    'Remember that the launch review is Friday.',
    7,
    'remember:assistant-1',
  );
  expect(result).toEqual({
    id: `timeline-${'a'.repeat(48)}`,
    idempotent: false,
  });
  expect(requests[0]).toContain(`POST ${STM_NOTES_OPS_PATH}`);
  expect(requests[0]).toContain('"domain":"stm-notes"');
  expect(requests[0]).toContain('launch review is Friday');
});

test('does not claim a save when the backend refuses it', async () => {
  await expect(
    saveTimelineMemory(
      backend({status: 422, body: '{"error":"invalid_envelope"}'}),
      'A note',
      7,
      'remember:assistant-1',
    ),
  ).rejects.toMatchObject({status: 422});
});

test('refuses legacy or browser backends before making a write request', async () => {
  const request = jest.fn();
  const legacy = {
    ...backend({status: 200, body: null}),
    getApiContract: async () => 'omi' as const,
    request,
  };
  await expect(
    saveTimelineMemory(legacy, 'A note', 7, 'remember:assistant-1'),
  ).rejects.toThrow('unavailable');
  expect(request).not.toHaveBeenCalled();
});

test('retries an uncertain reply with the same native write and record identities', async () => {
  const request = jest
    .fn()
    .mockRejectedValueOnce(new Error('reply lost after delivery'))
    .mockResolvedValueOnce({
      id: 'retry',
      status: 200,
      body: JSON.stringify({
        applied: {
          record_id: `timeline-${'a'.repeat(48)}`,
          revision: 'b'.repeat(64),
        },
        idempotent: true,
      }),
    });
  const prepared = await prepareTimelineMemory(
    {...backend({status: 200, body: null}), request},
    'A note that may have reached the server.',
    7,
    'remember:assistant-retry',
  );
  await expect(
    sendTimelineMemory(
      {...backend({status: 200, body: null}), request},
      prepared,
    ),
  ).rejects.toThrow('could not be confirmed');
  await expect(
    sendTimelineMemory(
      {...backend({status: 200, body: null}), request},
      prepared,
    ),
  ).resolves.toEqual({id: prepared.recordId, idempotent: true});
  const payloads = request.mock.calls.map(([input]) => JSON.parse(input.body));
  expect(payloads).toHaveLength(2);
  expect(payloads[0].write_id).toBe(payloads[1].write_id);
  expect(payloads[0].op.record_id).toBe(payloads[1].op.record_id);
});

test('rejects a successful-looking acknowledgement for a different memory', async () => {
  await expect(
    saveTimelineMemory(
      backend({
        status: 200,
        body: JSON.stringify({
          applied: {
            record_id: `timeline-${'b'.repeat(48)}`,
            revision: 'c'.repeat(64),
          },
          idempotent: false,
        }),
      }),
      'A note',
      7,
      'remember:assistant-mismatch',
    ),
  ).rejects.toThrow('did not match');
});
