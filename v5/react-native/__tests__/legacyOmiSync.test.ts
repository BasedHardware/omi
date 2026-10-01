import {
  LegacyOmiSyncError,
  isTransientLegacyOmiSyncError,
  omiSyncFilename,
  omiWalFromFramedPackets,
  syncLegacyOmiRecording,
} from '../src/legacyOmiSync';
import {encodeBase64} from '../src/base64';
import type {NativeHttpResponse, OmiBackend} from '../src/omiNative';

function framedPacket(opus: number[], seq = 1, fragment = 0): Uint8Array {
  return new Uint8Array([seq & 0xff, (seq >> 8) & 0xff, fragment, ...opus]);
}

function response(status: number, body: unknown): NativeHttpResponse {
  return {
    id: 'test',
    status,
    body: typeof body === 'string' ? body : JSON.stringify(body),
  };
}

function makeBackend(): {backend: OmiBackend; request: jest.Mock} {
  const request = jest.fn();
  const backend = {request} as unknown as OmiBackend;
  return {backend, request};
}

describe('omiWalFromFramedPackets', () => {
  test('strips the 3-byte wearable header and prefixes u32 LE lengths', () => {
    const wal = omiWalFromFramedPackets([
      framedPacket([0xaa, 0xbb]),
      framedPacket([0x01, 0x02, 0x03, 0x04], 2),
    ]);
    expect(Array.from(wal)).toEqual([
      2,
      0,
      0,
      0,
      0xaa,
      0xbb, //
      4,
      0,
      0,
      0,
      0x01,
      0x02,
      0x03,
      0x04,
    ]);
  });

  test('encodes sizes above 255 across all four bytes', () => {
    const wal = omiWalFromFramedPackets([
      framedPacket(new Array<number>(0x0102).fill(0x7f)),
    ]);
    expect(wal.length).toBe(4 + 0x0102);
    expect(wal[0]).toBe(0x02);
    expect(wal[1]).toBe(0x01);
    expect(wal[2]).toBe(0);
    expect(wal[3]).toBe(0);
  });

  test('rejects truncated packets', () => {
    expect(() => omiWalFromFramedPackets([new Uint8Array([1, 2])])).toThrow(
      /truncated/i,
    );
  });
});

describe('omiSyncFilename', () => {
  test('embeds the capture timestamp the lane parser reads', () => {
    expect(omiSyncFilename(1700000000000)).toBe(
      'omi-macos-ambient_1700000000000.bin',
    );
  });

  test('rejects malformed capture times', () => {
    expect(() => omiSyncFilename(0)).toThrow(/malformed/i);
    expect(() => omiSyncFilename(1.5)).toThrow(/malformed/i);
  });
});

describe('syncLegacyOmiRecording', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  const packets = [framedPacket([0xaa]), framedPacket([0xbb], 2)];

  test('uploads a WAL multipart part and polls the job to completion', async () => {
    const {backend, request} = makeBackend();
    request
      .mockResolvedValueOnce(
        response(202, {job_id: 'job-7', poll_after_ms: 1500}),
      )
      .mockResolvedValueOnce(response(200, {status: 'processing'}))
      .mockResolvedValueOnce(response(200, {status: 'completed'}));

    const pending = syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    });
    await jest.advanceTimersByTimeAsync(60_000);
    await expect(pending).resolves.toBeUndefined();

    const upload = request.mock.calls[0][0];
    expect(upload.method).toBe('POST');
    expect(upload.path).toBe('/v2/sync-local-files');
    expect(upload.expectedApiContract).toBe('omi');
    expect(upload.multipart).toEqual([
      {
        name: 'files',
        filename: 'omi-macos-ambient_1700000000000.bin',
        contentType: 'application/octet-stream',
        bytesBase64: encodeBase64(omiWalFromFramedPackets(packets)),
      },
    ]);

    expect(request.mock.calls[1][0].path).toBe('/v2/sync-local-files/job-7');
    expect(request.mock.calls[2][0].method).toBe('GET');
    expect(request).toHaveBeenCalledTimes(3);
  });

  test('returns immediately when the content claim already completed', async () => {
    const {backend, request} = makeBackend();
    request.mockResolvedValueOnce(
      response(202, {job_id: 'job-1', status: 'completed'}),
    );

    await syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test('maps a backfill rejection to an unrecoverable error', async () => {
    const {backend, request} = makeBackend();
    request.mockResolvedValueOnce(
      response(422, {code: 'backfill_lookback_exceeded'}),
    );

    await expect(
      syncLegacyOmiRecording(backend, {
        capturedAtMs: 1700000000000,
        packets,
      }),
    ).rejects.toMatchObject({unrecoverable: true, transient: false});
  });

  test.each([
    [500, true],
    [502, true],
    [429, true],
    [400, false],
  ])('maps upload status %i to transient=%s', async (status, transient) => {
    const {backend, request} = makeBackend();
    request.mockResolvedValueOnce(response(status, {}));

    const error = await syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    }).catch((thrown: unknown) => thrown);
    expect(error).toBeInstanceOf(LegacyOmiSyncError);
    expect(isTransientLegacyOmiSyncError(error)).toBe(transient);
  });

  test('treats a failed job as transient (retry is content-deduped)', async () => {
    const {backend, request} = makeBackend();
    request
      .mockResolvedValueOnce(response(202, {job_id: 'job-2'}))
      .mockResolvedValueOnce(response(200, {status: 'failed'}));

    const pending = syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    });
    pending.catch(() => undefined);
    await jest.advanceTimersByTimeAsync(2500);
    await expect(pending).rejects.toMatchObject({transient: true});
  });

  test('treats an expired job (404) as transient', async () => {
    const {backend, request} = makeBackend();
    request
      .mockResolvedValueOnce(response(202, {job_id: 'job-3'}))
      .mockResolvedValueOnce(response(404, {}));

    const pending = syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    });
    pending.catch(() => undefined);
    await jest.advanceTimersByTimeAsync(2500);
    await expect(pending).rejects.toMatchObject({transient: true});
  });

  test('gives up polling as transient after the attempt budget', async () => {
    const {backend, request} = makeBackend();
    request.mockImplementation(async (call: {method: string}) =>
      call.method === 'POST'
        ? response(202, {job_id: 'job-4'})
        : response(200, {status: 'pending'}),
    );

    const pending = syncLegacyOmiRecording(backend, {
      capturedAtMs: 1700000000000,
      packets,
    });
    pending.catch(() => undefined);
    // 12 attempts with exponential backoff 1s..15s ≈ 2.5 minutes.
    await jest.advanceTimersByTimeAsync(200_000);
    await expect(pending).rejects.toMatchObject({transient: true});
    expect(
      request.mock.calls.filter((c: any[]) => c[0].method === 'GET'),
    ).toHaveLength(12);
  });

  test('flags transport failures as transient', () => {
    expect(
      isTransientLegacyOmiSyncError(
        Object.assign(new Error('x'), {code: 'OMI_HTTP_TRANSPORT'}),
      ),
    ).toBe(true);
    expect(isTransientLegacyOmiSyncError(new TypeError('boom'))).toBe(true);
    expect(isTransientLegacyOmiSyncError(new Error('nope'))).toBe(false);
  });
});
