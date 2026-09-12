import {
  calendarCaptureGapSpan,
  captureGapHeaderCopy,
  captureGapTimeRangeCopy,
  loadOmiCalendarCaptureGaps,
  parseOmiCalendarCaptureGaps,
} from './legacyOmiCalendarCaptureGaps';
import type {OmiBackend} from './omiNativeTypes';

test('formats GET capture-gap clocks like Flutter h:mm a ranges', () => {
  const start = Date.parse('2026-09-07T15:00:00.000Z');
  const end = Date.parse('2026-09-07T16:30:00.000Z');
  expect(captureGapTimeRangeCopy(start, end)).toBe(
    `${new Date(start).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })} – ${new Date(end).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    })}`,
  );
  expect(captureGapHeaderCopy(2)).toBe('Not captured (2)');
  expect(captureGapHeaderCopy(0)).toBe('');
});

test('spans GET capture-gaps from loaded local conversation days', () => {
  const noon = '2026-09-07T12:00:00.000Z';
  const later = '2026-09-09T12:00:00.000Z';
  const first = new Date(Date.parse(noon));
  const last = new Date(Date.parse(later));
  expect(
    calendarCaptureGapSpan([
      {startedAt: noon, createdAt: noon},
      {startedAt: later, createdAt: later},
      {
        startedAt: new Date(0).toISOString(),
        createdAt: new Date(0).toISOString(),
      },
    ]),
  ).toEqual({
    start: new Date(
      first.getFullYear(),
      first.getMonth(),
      first.getDate(),
    ).toISOString(),
    end: new Date(
      last.getFullYear(),
      last.getMonth(),
      last.getDate() + 1,
    ).toISOString(),
  });
  expect(calendarCaptureGapSpan([])).toBeNull();
});

test('parses GET capture-gap titles and omits empty titles', () => {
  const rows = parseOmiCalendarCaptureGaps(
    JSON.stringify([
      {
        event_id: 'event-standup',
        title: 'Standup',
        start_time: '2026-09-07T15:00:00.000Z',
        end_time: '2026-09-07T15:30:00.000Z',
        status: 'confirmed',
        coverage: 'not_captured',
      },
      {
        event_id: 'event-empty',
        title: ' \t',
        start_time: '2026-09-07T16:00:00.000Z',
        end_time: '2026-09-07T17:00:00.000Z',
      },
    ]),
  );
  expect(rows).toEqual([
    {
      eventId: 'event-standup',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when event_id exceeds 256', () => {
  const eventId = 'e'.repeat(257);
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: eventId,
          title: 'Standup',
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T15:30:00.000Z',
        },
        {
          event_id: 'event-neighbor',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: '2026-09-07T17:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId,
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T17:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when title exceeds 10000', () => {
  const title = 'S'.repeat(10001);
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-long',
          title,
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T15:30:00.000Z',
        },
        {
          event_id: 'event-neighbor',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: '2026-09-07T17:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-long',
      title,
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T17:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when status or coverage exceeds 256', () => {
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-long-status',
          title: 'Standup',
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T15:30:00.000Z',
          status: 'x'.repeat(257),
          coverage: 'y'.repeat(257),
        },
        {
          event_id: 'event-neighbor',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: '2026-09-07T17:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-long-status',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T17:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when status or coverage exceeds 10000', () => {
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-long-status',
          title: 'Standup',
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T15:30:00.000Z',
          status: 'x'.repeat(10001),
          coverage: 'y'.repeat(10001),
        },
        {
          event_id: 'event-neighbor',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: '2026-09-07T17:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-long-status',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T17:00:00.000Z'),
    },
  ]);
});

test('names empty GET capture-gap status as omitted instead of hiding neighbors', () => {
  const rows = parseOmiCalendarCaptureGaps(
    JSON.stringify([
      {
        event_id: 'event-empty-status',
        title: 'Standup',
        start_time: '2026-09-07T15:00:00.000Z',
        end_time: '2026-09-07T15:30:00.000Z',
        status: '',
        coverage: '',
      },
      {
        event_id: 'event-neighbor',
        title: 'Retro',
        start_time: '2026-09-07T16:00:00.000Z',
        end_time: '2026-09-07T17:00:00.000Z',
      },
    ]),
  );
  expect(rows).toEqual([
    {
      eventId: 'event-empty-status',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T17:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when start_time or end_time exceeds 100', () => {
  const startTime = `2026-09-07T15:00:00.${'0'.repeat(80)}Z`;
  const endTime = `2026-09-07T16:30:00.${'0'.repeat(80)}Z`;
  expect(startTime.length).toBe(101);
  expect(endTime.length).toBe(101);
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-long-start',
          title: 'Standup',
          start_time: startTime,
          end_time: '2026-09-07T15:30:00.000Z',
        },
        {
          event_id: 'event-long-end',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: endTime,
        },
        {
          event_id: 'event-neighbor',
          title: 'Review',
          start_time: '2026-09-07T18:00:00.000Z',
          end_time: '2026-09-07T19:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-long-start',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-long-end',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T16:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Review',
      startMs: Date.parse('2026-09-07T18:00:00.000Z'),
      endMs: Date.parse('2026-09-07T19:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when start_time or end_time uses hour-only offsets Dart DateTime.tryParse accepts', () => {
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-hour-offset',
          title: 'Standup',
          start_time: '2026-09-07T15:00:00+00',
          end_time: '2026-09-07T15:30:00+00',
        },
        {
          event_id: 'event-neighbor',
          title: 'Review',
          start_time: '2026-09-07T18:00:00.000Z',
          end_time: '2026-09-07T19:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-hour-offset',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Review',
      startMs: Date.parse('2026-09-07T18:00:00.000Z'),
      endMs: Date.parse('2026-09-07T19:00:00.000Z'),
    },
  ]);
});

test('keeps GET capture gaps when start_time or end_time exceeds 10000', () => {
  const startTime = `2026-09-07T15:00:00.${'0'.repeat(9980)}Z`;
  const endTime = `2026-09-07T16:30:00.${'0'.repeat(9980)}Z`;
  expect(startTime.length).toBe(10001);
  expect(endTime.length).toBe(10001);
  expect(
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-long-start',
          title: 'Standup',
          start_time: startTime,
          end_time: '2026-09-07T15:30:00.000Z',
        },
        {
          event_id: 'event-long-end',
          title: 'Retro',
          start_time: '2026-09-07T16:00:00.000Z',
          end_time: endTime,
        },
        {
          event_id: 'event-neighbor',
          title: 'Review',
          start_time: '2026-09-07T18:00:00.000Z',
          end_time: '2026-09-07T19:00:00.000Z',
        },
      ]),
    ),
  ).toEqual([
    {
      eventId: 'event-long-start',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
    {
      eventId: 'event-long-end',
      title: 'Retro',
      startMs: Date.parse('2026-09-07T16:00:00.000Z'),
      endMs: Date.parse('2026-09-07T16:30:00.000Z'),
    },
    {
      eventId: 'event-neighbor',
      title: 'Review',
      startMs: Date.parse('2026-09-07T18:00:00.000Z'),
      endMs: Date.parse('2026-09-07T19:00:00.000Z'),
    },
  ]);
});

test('does not omit neighboring GET capture gaps when the catalogue exceeds 1000', () => {
  const rows = Array.from({length: 1001}, (_, index) => ({
    event_id: `event-${index}`,
    title: `Event ${index}`,
    start_time: '2026-09-07T15:00:00.000Z',
    end_time: '2026-09-07T15:30:00.000Z',
  }));
  const gaps = parseOmiCalendarCaptureGaps(JSON.stringify(rows));
  expect(gaps[0]).toEqual({
    eventId: 'event-0',
    title: 'Event 0',
    startMs: Date.parse('2026-09-07T15:00:00.000Z'),
    endMs: Date.parse('2026-09-07T15:30:00.000Z'),
  });
  expect(gaps[1000]?.eventId).toBe('event-1000');
  expect(gaps).toHaveLength(1001);
});

test('fails closed for malformed GET capture gaps', () => {
  expect(() =>
    parseOmiCalendarCaptureGaps(JSON.stringify({event_id: 'event-1'})),
  ).toThrow();
  expect(() =>
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-1',
          title: 1,
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T16:00:00.000Z',
        },
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-1',
          title: 'Standup',
          start_time: 'nope',
          end_time: '2026-09-07T16:00:00.000Z',
        },
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-1',
          title: 'Standup',
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T16:00:00.000Z',
          status: 1,
        },
      ]),
    ),
  ).toThrow();
  expect(() =>
    parseOmiCalendarCaptureGaps(
      JSON.stringify([
        {
          event_id: 'event-1',
          title: 'Standup',
          start_time: '2026-09-07T15:00:00.000Z',
          end_time: '2026-09-07T16:00:00.000Z',
        },
        {
          event_id: 'event-1',
          title: 'Dup',
          start_time: '2026-09-07T17:00:00.000Z',
          end_time: '2026-09-07T18:00:00.000Z',
        },
      ]),
    ),
  ).toThrow();
});

test('loadOmiCalendarCaptureGaps names resolved GET gaps and omits failures', async () => {
  const span = {
    start: '2026-09-07T00:00:00.000Z',
    end: '2026-09-08T00:00:00.000Z',
  };
  const request = jest.fn(async () => ({
    id: 'gaps',
    status: 200,
    body: JSON.stringify([
      {
        event_id: 'event-standup',
        title: 'Standup',
        start_time: '2026-09-07T15:00:00.000Z',
        end_time: '2026-09-07T15:30:00.000Z',
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiCalendarCaptureGaps(backend, span)).toEqual([
    {
      eventId: 'event-standup',
      title: 'Standup',
      startMs: Date.parse('2026-09-07T15:00:00.000Z'),
      endMs: Date.parse('2026-09-07T15:30:00.000Z'),
    },
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/calendar/capture-gaps?start=${encodeURIComponent(
      span.start,
    )}&end=${encodeURIComponent(span.end)}`,
  });
  request.mockResolvedValueOnce({id: 'gaps', status: 400, body: '[]'});
  expect(await loadOmiCalendarCaptureGaps(backend, span)).toEqual([]);
  request.mockResolvedValueOnce({id: 'gaps', status: 200, body: '{'});
  expect(await loadOmiCalendarCaptureGaps(backend, span)).toEqual([]);
});
