const createMemory = require('../../creates/create_memory');

describe('creates.create_memory', () => {
  const body = createMemory.operation.perform.body;

  it('returns the backend create-memory contract instead of undefined', async () => {
    const payload = await body(
      {},
      {
        inputData: {
          text: 'remember this',
          source: 'other_text',
          language: 'en',
        },
      }
    );

    expect(payload).toEqual({
      text: 'remember this',
      source: 'other_text',
      language: 'en',
    });
    expect(payload).not.toHaveProperty('started_at');
    expect(payload).not.toHaveProperty('finished_at');
    expect(payload).not.toHaveProperty('geolocation');
  });

  it('forwards optional timestamps and geolocation', async () => {
    const geo = { latitude: 37.8, longitude: -122.4, address: 'SF' };
    const payload = await body(
      {},
      {
        inputData: {
          text: 'walked downtown',
          source: 'audio_transcript',
          language: 'en',
          started_at: '2026-09-12T10:00:00Z',
          finished_at: '2026-09-12T10:05:00Z',
          geolocation: geo,
        },
      }
    );

    expect(payload.started_at).toBe('2026-09-12T10:00:00Z');
    expect(payload.finished_at).toBe('2026-09-12T10:05:00Z');
    expect(payload.geolocation).toEqual(geo);
  });
});
