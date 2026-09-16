import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  conversationFirstPartySummaryCopy,
  conversationPhotoAnalyzingCopy,
  conversationPhotoDiscardedCopy,
  conversationPhotoUnavailableCopy,
  conversationNoFolderCopy,
  conversationUnknownAppCopy,
  conversationUnknownLocationCopy,
  desktopBackendServiceCopy,
  transcriptSttUnknownCopy,
  transcriptSttOmiFallbackCopy,
} from './desktopReadClient';
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
  expect(value.actionItems).toEqual([]);
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

test('names GET transcript start/end numeric strings', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          start: '0.25',
          end: '4.5',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
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

test('names Flutter TranscriptWidget padded GET start instead of remapping to a clock', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          start: '  0.25  ',
          end: '4.5',
        },
      ],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          start: '0.25 ',
          end: '4.5',
        },
      ],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          start: '\u00850.25',
          end: '4.5',
        },
      ],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('names omitted GET transcript speaker as Flutter SPEAKER_00 instead of hiding Speaker 1', async () => {
  const {speaker: _omitted, ...withoutSpeaker} = fixture.transcript_segments[0];
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [withoutSpeaker],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
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
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          speaker: null,
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
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

test('keeps GET calendar event title and attendees and omits missing events', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: ['Alex Chen', ' \t', 'sam@example.com'],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  const linked = await loadLegacyConversationDetail(backend, fixture.id);
  expect(linked.calendarEvent).toMatchObject({
    title: 'Standup',
    attendees: ['Alex Chen', ' \t', 'sam@example.com'],
  });
  expect(linked.calendarEvent?.startCopy).toEqual(expect.any(String));
  expect(linked.calendarEvent?.startCopy).not.toBe('');
  expect(linked.calendarEvent?.endCopy).toEqual(expect.any(String));
  expect(linked.calendarEvent?.endCopy).not.toBe('');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-2',
        title: ' \n',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  const untitled = await loadLegacyConversationDetail(backend, fixture.id);
  expect(untitled.calendarEvent).toMatchObject({
    title: ' \n',
    attendees: [],
  });
  expect(untitled.calendarEvent).not.toHaveProperty('shareMailto');
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).toBeUndefined();
});

test('names Flutter CalendarEventDetailsSheet empty GET html_link whitespace', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: 'https://calendar.google.com/calendar/event?eid=standup',
      },
    }),
  );
  const linked = await loadLegacyConversationDetail(backend, fixture.id);
  expect(linked.title).toBe(fixture.structured.title);
  expect(linked.calendarEvent).toMatchObject({
    title: 'Standup',
    htmlLink: 'https://calendar.google.com/calendar/event?eid=standup',
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-empty-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: ' \t',
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).toMatchObject({htmlLink: ' \t'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-next-line-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: '\u0085',
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).toMatchObject({htmlLink: '\u0085'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-blank-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: '',
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).toMatchObject({htmlLink: ''});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-null-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: null,
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).not.toHaveProperty('htmlLink');
});

test('keeps GET calendar event when html_link exceeds 10000', async () => {
  const htmlLink = `https://calendar.google.com/calendar/event?eid=${'a'.repeat(
    10000,
  )}`;
  expect(htmlLink.length).toBeGreaterThan(10000);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-long-link',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: htmlLink,
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.calendarEvent?.htmlLink).toBe(htmlLink);
});

test('keeps GET calendar attendee_emails Share with attendees Flutter paints', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-share',
        title: 'Standup',
        attendees: ['Alex Chen'],
        attendee_emails: ['alex@example.com', ' \t', 'sam@example.com'],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      title: 'Standup',
      attendees: ['Alex Chen'],
      shareMailto: `mailto:alex@example.com, \t,sam@example.com?subject=${encodeURIComponent(
        'Notes: Standup',
      )}`,
    },
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-empty-emails',
        title: 'Standup',
        attendees: [],
        attendee_emails: [' \t', ''],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      shareMailto: `mailto: \t,?subject=${encodeURIComponent('Notes: Standup')}`,
    },
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-omit-emails',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).not.toHaveProperty('shareMailto');
});

test('keeps GET calendar attendee_emails padded Share mailto Flutter paints', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-padded-email',
        title: 'Standup',
        attendees: ['Alex Chen'],
        attendee_emails: ['  sam@example.com  '],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      shareMailto: `mailto:  sam@example.com  ?subject=${encodeURIComponent(
        'Notes: Standup',
      )}`,
    },
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-trailing-email',
        title: 'Standup',
        attendees: ['Alex Chen'],
        attendee_emails: ['sam@example.com '],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      shareMailto: `mailto:sam@example.com ?subject=${encodeURIComponent(
        'Notes: Standup',
      )}`,
    },
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-nel-email',
        title: 'Standup',
        attendees: ['Alex Chen'],
        attendee_emails: ['\u0085sam@example.com'],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      shareMailto: `mailto:\u0085sam@example.com?subject=${encodeURIComponent(
        'Notes: Standup',
      )}`,
    },
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-exact-email',
        title: 'Standup',
        attendees: ['Alex Chen'],
        attendee_emails: ['sam@example.com'],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    calendarEvent: {
      shareMailto: `mailto:sam@example.com?subject=${encodeURIComponent(
        'Notes: Standup',
      )}`,
    },
  });
});

test('keeps GET calendar event attendees when more than 1000', async () => {
  const attendees = Array.from({length: 1001}, (_, index) => `Person ${index}`);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-long',
        title: 'Standup',
        attendees,
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.calendarEvent).toMatchObject({
    title: 'Standup',
    attendees,
  });
});

test('keeps GET calendar event when start_time or end_time exceeds 100', async () => {
  const startTime = `2026-09-10T15:00:00.${'0'.repeat(80)}Z`;
  const endTime = `2026-09-10T16:00:00.${'0'.repeat(80)}Z`;
  expect(startTime.length).toBe(101);
  expect(endTime.length).toBe(101);
  const clock = (iso: string) =>
    new Date(Date.parse(iso)).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-long-clock',
        title: 'Standup',
        attendees: [],
        start_time: startTime,
        end_time: endTime,
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.calendarEvent).toEqual({
    title: 'Standup',
    attendees: [],
    startCopy: clock('2026-09-10T15:00:00.000Z'),
    endCopy: clock('2026-09-10T16:00:00.000Z'),
  });
});

test('keeps GET calendar event when start_time or end_time exceeds 10000', async () => {
  const startTime = `2026-09-10T15:00:00.${'0'.repeat(9980)}Z`;
  const endTime = `2026-09-10T16:00:00.${'0'.repeat(9980)}Z`;
  expect(startTime.length).toBe(10001);
  expect(endTime.length).toBe(10001);
  const clock = (iso: string) =>
    new Date(Date.parse(iso)).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-long-clock',
        title: 'Standup',
        attendees: [],
        start_time: startTime,
        end_time: endTime,
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.calendarEvent).toEqual({
    title: 'Standup',
    attendees: [],
    startCopy: clock('2026-09-10T15:00:00.000Z'),
    endCopy: clock('2026-09-10T16:00:00.000Z'),
  });
});

test('keeps GET calendar event when start_time or end_time uses hour-only offsets Dart DateTime.tryParse accepts', async () => {
  const clock = (iso: string) =>
    new Date(Date.parse(iso)).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-hour-offset',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00+00',
        end_time: '2026-09-10T16:00:00+00',
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.calendarEvent).toEqual({
    title: 'Standup',
    attendees: [],
    startCopy: clock('2026-09-10T15:00:00.000Z'),
    endCopy: clock('2026-09-10T16:00:00.000Z'),
  });
});

test('names Flutter TranscriptWidget empty GET translations', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations: [
            {lang: 'es', text: 'Hola alli'},
            {lang: 'fr', text: ' \t'},
            {lang: 'de', text: ''},
            {lang: 'it', text: '\u0085'},
          ],
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        translations: ['Hola alli', ' \t', '', '\u0085'],
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations: [{lang: 'es', text: ''}],
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        translations: [''],
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations: [],
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
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

test('keeps GET conversation transcript translations when more than 32', async () => {
  const translations = Array.from({length: 33}, (_, index) => ({
    lang: `l${index}`,
    text: `copy ${index}`,
  }));
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations,
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        translations: translations.map(row => row.text),
      },
    ],
  });
});

test('keeps GET conversation transcript translation language longer than 32', async () => {
  const lang = 'x'.repeat(33);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations: [{lang, text: 'Hola alli'}],
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        translations: ['Hola alli'],
      },
    ],
  });
});

test('names Flutter TranscriptWidget empty GET text', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          text: '',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 0,
          end: 1,
        },
        {
          text: ' \t',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 1,
          end: 2,
        },
        {
          text: '\u0085',
          speaker: 'SPEAKER_00',
          is_user: false,
          start: 2,
          end: 3,
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: '',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0,
        end: 1,
      },
      {
        text: ' \t',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 1,
        end: 2,
      },
      {
        text: '\u0085',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 2,
        end: 3,
      },
    ],
  });
});

test('names GET transcript stt_provider unknown as Flutter Omi', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: 'deepgram',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        sttProvider: 'Deepgram',
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: 'whisper-cloudflare',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        sttProvider: transcriptSttOmiFallbackCopy(),
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: '',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        sttProvider: transcriptSttUnknownCopy(),
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: ' \t\u0085 ',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        sttProvider: transcriptSttOmiFallbackCopy(),
      },
    ],
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: '  deepgram  ',
        },
      ],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toEqual({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
        sttProvider: transcriptSttOmiFallbackCopy(),
      },
    ],
  });
});

test('keeps GET transcript when speaker or stt_provider exceeds 256', async () => {
  const speaker = 'S'.repeat(257);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          speaker,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker,
            isUser: true,
            start: 0.25,
            end: 4.5,
          },
        ],
      },
    },
  );
  const sttProvider = 'p'.repeat(257);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: sttProvider,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
            sttProvider: transcriptSttOmiFallbackCopy(),
          },
        ],
      },
    },
  );
});

test('keeps GET conversation detail when speaker or stt_provider exceeds 10000', async () => {
  const speaker = 'S'.repeat(10001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          speaker,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker,
            isUser: true,
            start: 0.25,
            end: 4.5,
          },
        ],
      },
    },
  );
  const sttProvider = 'p'.repeat(10001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          stt_provider: sttProvider,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
            sttProvider: transcriptSttOmiFallbackCopy(),
          },
        ],
      },
    },
  );
});

test('keeps GET conversation detail when transcript text exceeds 100000', async () => {
  const text = 't'.repeat(100001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          text,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
          },
        ],
      },
    },
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: text}],
      plugins_results: [],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBe(text);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: {text},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBe(text);
});

test('keeps GET conversation detail when transcript text exceeds 1000000', async () => {
  const text = 't'.repeat(1000001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          text,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
          },
        ],
      },
    },
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: text}],
      plugins_results: [],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBe(text);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: {text},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBe(text);
});

test('keeps GET conversation detail when person_id or folder_id exceeds 256', async () => {
  const folderId = 'f'.repeat(257);
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([{id: folderId, name: 'Work'}]),
      };
    }
    return response({
      ...fixture,
      folder_id: folderId,
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      summary: fixture.structured.overview,
      folderName: 'Work',
    },
  );
  const personId = 'p'.repeat(257);
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([{id: personId, name: 'Alex Chen'}]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          person_id: personId,
        },
      ],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
            personName: 'Alex Chen',
          },
        ],
      },
    },
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      folder_id: null,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          person_id: null,
        },
      ],
    }),
  );
  const omitted = await loadLegacyConversationDetail(backend, fixture.id);
  expect(omitted).toMatchObject({
    title: fixture.structured.title,
    transcript: {
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
    },
  });
  expect(omitted.folderName).toBe(conversationNoFolderCopy());
  expect(JSON.stringify(omitted)).not.toContain('folder-work');
  expect(
    omitted.transcript.status === 'loaded' ? omitted.transcript.segments[0] : null,
  ).not.toHaveProperty('personName');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      folder_id: 1,
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          person_id: 1,
        },
      ],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('keeps GET conversation detail when person_id, folder_id, or event_id exceeds 10000', async () => {
  const folderId = 'f'.repeat(10001);
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([{id: folderId, name: 'Work'}]),
      };
    }
    return response({
      ...fixture,
      folder_id: folderId,
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      summary: fixture.structured.overview,
      folderName: 'Work',
    },
  );
  const personId = 'p'.repeat(10001);
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([{id: personId, name: 'Alex Chen'}]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          person_id: personId,
        },
      ],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      transcript: {
        status: 'loaded',
        segments: [
          {
            text: fixture.transcript_segments[0].text,
            speaker: 'SPEAKER_00',
            isUser: true,
            start: 0.25,
            end: 4.5,
            personName: 'Alex Chen',
          },
        ],
      },
    },
  );
  const eventId = 'e'.repeat(10001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: eventId,
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    title: fixture.structured.title,
    calendarEvent: {title: 'Standup'},
  });
});

test('keeps GET conversation detail when the conversation id exceeds 256', async () => {
  const id = 'c'.repeat(257);
  mockRequest.mockResolvedValue(response({...fixture, id}));
  expect(await loadLegacyConversationDetail(backend, id)).toMatchObject({
    id,
    title: fixture.structured.title,
    summary: fixture.structured.overview,
  });
  expect(mockRequest).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/conversations/${encodeURIComponent(id)}`,
  });
});

test('keeps GET conversation detail when the conversation id exceeds 10000', async () => {
  const id = 'c'.repeat(10001);
  mockRequest.mockResolvedValue(response({...fixture, id}));
  expect(await loadLegacyConversationDetail(backend, id)).toMatchObject({
    id,
    title: fixture.structured.title,
    summary: fixture.structured.overview,
  });
  expect(mockRequest).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/conversations/${encodeURIComponent(id)}`,
  });
});

test('fails closed when the conversation id exceeds 1000000', async () => {
  mockRequest.mockClear();
  await expect(
    loadLegacyConversationDetail(backend, 'c'.repeat(1_000_001)),
  ).rejects.toMatchObject({kind: 'invalid'});
  expect(mockRequest).not.toHaveBeenCalled();
});

test('fails closed for malformed GET calendar_event', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: 'not-an-object',
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: 'Alex',
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: [],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
        html_link: 1,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: [],
        attendee_emails: 'alex@example.com',
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: [],
        attendee_emails: [1],
        start_time: '2026-09-10T15:00:00.000Z',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      calendar_event: {
        event_id: 'evt-1',
        title: 'Standup',
        attendees: [],
        start_time: 'not-a-date',
        end_time: '2026-09-10T16:00:00.000Z',
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('keeps GET photo counts and captions and omits empty lists', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {description: 'Whiteboard notes', base64: ''},
        {description: ' \t', base64: ''},
        {id: 'three', base64: ''},
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      photoCount: 3,
      photoCaptions: [
        'Whiteboard notes',
        ' \t',
        conversationPhotoAnalyzingCopy(),
      ],
    },
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [],
    }),
  );
  const empty = await loadLegacyConversationDetail(backend, fixture.id);
  expect(empty).not.toHaveProperty('photoCount');
  expect(empty).not.toHaveProperty('photoCaptions');
  mockRequest.mockResolvedValue(response(fixture));
  const missing = await loadLegacyConversationDetail(backend, fixture.id);
  expect(missing).not.toHaveProperty('photoCount');
  expect(missing).not.toHaveProperty('photoCaptions');
});

test('keeps GET conversation photos when more than 1000', async () => {
  const photos = Array.from({length: 1001}, (_, index) => ({
    description: `Photo ${index}`,
    base64: '',
  }));
  mockRequest.mockResolvedValue(response({...fixture, photos}));
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      photoCount: 1001,
      photoCaptions: photos.map(row => row.description),
    },
  );
});

test('keeps GET conversation photos when content_type exceeds 256', async () => {
  const png =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  const contentType = `image/${'a'.repeat(251)}`;
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {
          description: 'Whiteboard notes',
          base64: png,
          content_type: contentType,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      photoCount: 1,
      photoCaptions: ['Whiteboard notes'],
      photoRows: [
        {
          caption: 'Whiteboard notes',
          imageUri: `data:${contentType};base64,${png}`,
        },
      ],
      transcript: {
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
      },
    },
  );
});

test('keeps GET conversation photos when content_type exceeds 10000', async () => {
  const png =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  const contentType = `image/${'a'.repeat(9995)}`;
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {
          description: 'Whiteboard notes',
          base64: png,
          content_type: contentType,
        },
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      photoCount: 1,
      photoCaptions: ['Whiteboard notes'],
      photoRows: [
        {
          caption: 'Whiteboard notes',
          imageUri: `data:${contentType};base64,${png}`,
        },
      ],
      transcript: {
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
      },
    },
  );
});

test('names GET discarded photos and photos still analyzing', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {description: 'Whiteboard notes', base64: ''},
        {description: 'ignored caption', discarded: true, base64: ''},
        {id: 'pending', base64: ''},
        {description: '   ', discarded: false, base64: ''},
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      photoCount: 4,
      photoCaptions: [
        'Whiteboard notes',
        conversationPhotoDiscardedCopy(),
        conversationPhotoAnalyzingCopy(),
        '   ',
      ],
    },
  );
});

test('names Flutter MediaViewerPage whitespace GET photo descriptions instead of omitting the caption', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {description: 'Whiteboard notes', base64: ''},
        {description: ' \t', base64: ''},
        {description: '', base64: ''},
        {id: 'pending', base64: ''},
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      photoCount: 4,
      photoCaptions: [
        'Whiteboard notes',
        ' \t',
        conversationPhotoAnalyzingCopy(),
      ],
    },
  );
  const whitespace = await loadLegacyConversationDetail(backend, fixture.id);
  expect(whitespace.photoRows?.[1]).toEqual(
    expect.objectContaining({caption: ' \t'}),
  );
  expect(whitespace.photoRows?.[2]).not.toHaveProperty('caption');
});

test('names GET invalid inline photo File unavailable and omits storage-only photos', async () => {
  const png =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {
          description: 'Whiteboard notes',
          base64: png,
          content_type: 'image/png',
        },
        {description: 'No bytes', base64: ''},
        {description: 'Whitespace', base64: ' \t'},
        {description: 'Corrupt', base64: '!!!!'},
        {
          id: 'stored',
          storage_id: 'storage-1',
          description: 'Stored elsewhere',
          base64: '',
        },
        {
          description: 'Stored empty',
          base64: '',
          storage_id: 'storage-1',
        },
      ],
    }),
  );
  const value = await loadLegacyConversationDetail(backend, fixture.id);
  expect(value).toMatchObject({
    photoCount: 6,
    photoCaptions: [
      'Whiteboard notes',
      'No bytes',
      'Whitespace',
      'Corrupt',
      'Stored elsewhere',
      'Stored empty',
    ],
    photoRows: [
      {
        caption: 'Whiteboard notes',
        imageUri: `data:image/png;base64,${png}`,
      },
      {caption: 'No bytes', unavailableCopy: conversationPhotoUnavailableCopy()},
      {caption: 'Whitespace', unavailableCopy: conversationPhotoUnavailableCopy()},
      {caption: 'Corrupt', unavailableCopy: conversationPhotoUnavailableCopy()},
      {caption: 'Stored elsewhere'},
      {caption: 'Stored empty'},
    ],
  });
  expect(
    mockRequest.mock.calls.map(call => (call[0] as {path: string}).path),
  ).toEqual(['/v1/conversations/conversation%2Fone']);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{description: 'Notes', base64: png}],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      photoRows: [
        {
          caption: 'Notes',
          imageUri: `data:image/jpeg;base64,${png}`,
        },
      ],
    },
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{base64: 1}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('fails closed for malformed GET photos', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: 'not-an-array',
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{description: 1}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{discarded: 1}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{description: 'Whiteboard notes'}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [{base64: null}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('names GET folder name when folders resolve and No Folder otherwise', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([
          {id: 'folder-work', name: 'Work', color: '#3B82F6', icon: '💼'},
        ]),
      };
    }
    return response({...fixture, folder_id: 'folder-work'});
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      folderName: 'Work',
      folderColor: '#3B82F6',
      folderIcon: '💼',
    }),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([
          {id: ' \t', name: 'Whitespace id'},
          {id: '', name: 'Blank id'},
        ]),
      };
    }
    return response({...fixture, folder_id: ' \t'});
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({folderName: 'Whitespace id'}),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([{id: '', name: 'Blank id'}]),
      };
    }
    return response({...fixture, folder_id: ''});
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({folderName: 'Blank id'}),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([{id: 'folder-other', name: 'Other'}]),
      };
    }
    return response({...fixture, folder_id: 'folder-work'});
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).folderName,
  ).toBe(conversationNoFolderCopy());
  expect(
    JSON.stringify(await loadLegacyConversationDetail(backend, fixture.id)),
  ).not.toContain('folder-work');
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {id: 'folders', status: 500, body: '[]'};
    }
    return response({...fixture, folder_id: 'folder-work'});
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).folderName,
  ).toBe(conversationNoFolderCopy());
  expect(
    JSON.stringify(await loadLegacyConversationDetail(backend, fixture.id)),
  ).not.toContain('folder-work');
  mockRequest.mockReset().mockResolvedValue(response(fixture));
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      folderName: conversationNoFolderCopy(),
    }),
  );
  expect(mockRequest).toHaveBeenCalledTimes(1);
  expect(mockRequest.mock.calls[0][0].path).not.toContain('/v1/folders');
});

test('names GET omitted folder color as Flutter #6B7280', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {
        id: 'folders',
        status: 200,
        body: JSON.stringify([{id: 'folder-work', name: 'Work'}]),
      };
    }
    return response({...fixture, folder_id: 'folder-work'});
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      folderName: 'Work',
      folderColor: '#6B7280',
    }),
  );
  mockRequest.mockReset().mockResolvedValue(response(fixture));
});

test('names Flutter ExpandableTextWidget empty GET external_data text instead of omitting it', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [],
      external_data: {text: 'Imported Slack thread'},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBe('Imported Slack thread');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: {text: ' \t\n'},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBe(' \t\n');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: {text: ''},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBe('');
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).externalText,
  ).toBeUndefined();
});

test('fails closed for malformed GET external_data', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: 'not-an-object',
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      external_data: {text: 1},
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('names GET people names on transcript segments and omits unresolved ids', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([{id: 'person-alex', name: 'Alex Chen'}]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_00',
          person_id: 'person-alex',
        },
      ],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toMatchObject({
    status: 'loaded',
    segments: [{personName: 'Alex Chen'}],
  });
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([
          {id: ' \t', name: 'Whitespace id'},
          {id: '', name: 'Blank id'},
        ]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_00',
          person_id: ' \t',
        },
      ],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toMatchObject({
    status: 'loaded',
    segments: [{personName: 'Whitespace id'}],
  });
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([{id: '', name: 'Blank id'}]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_00',
          person_id: '',
        },
      ],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toMatchObject({
    status: 'loaded',
    segments: [{personName: 'Blank id'}],
  });
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([{id: 'person-other', name: 'Sam'}]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          person_id: 'person-alex',
        },
      ],
    });
  });
  const unresolvedDetail = await loadLegacyConversationDetail(
    backend,
    fixture.id,
  );
  const unresolved = unresolvedDetail.transcript;
  expect(unresolved).toMatchObject({
    status: 'loaded',
    segments: [
      {
        text: fixture.transcript_segments[0].text,
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
  expect(unresolvedDetail.peopleError).toBeUndefined();
  expect(
    unresolved.status === 'loaded' ? unresolved.segments[0] : null,
  ).not.toHaveProperty('personName');
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {id: 'people', status: 500, body: '[]'};
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          person_id: 'person-alex',
        },
      ],
    });
  });
  const failedPeopleDetail = await loadLegacyConversationDetail(
    backend,
    fixture.id,
  );
  const failedPeople = failedPeopleDetail.transcript;
  expect(failedPeople).toMatchObject({
    status: 'loaded',
    segments: [{text: fixture.transcript_segments[0].text}],
  });
  expect(failedPeopleDetail.peopleError).toBeUndefined();
  expect(
    failedPeople.status === 'loaded' ? failedPeople.segments[0] : null,
  ).not.toHaveProperty('personName');
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_00',
          person_id: 'person-alex',
        },
      ],
    });
  });
  const thrownPeople = await loadLegacyConversationDetail(backend, fixture.id);
  expect(thrownPeople.peopleError).toBe(desktopBackendServiceCopy);
  expect(
    thrownPeople.transcript.status === 'loaded'
      ? thrownPeople.transcript.segments[0]
      : null,
  ).not.toHaveProperty('personName');
  mockRequest.mockReset().mockResolvedValue(response(fixture));
  await loadLegacyConversationDetail(backend, fixture.id);
  expect(mockRequest).toHaveBeenCalledTimes(1);
});

test('names Flutter TranscriptWidget empty GET people names', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: 'people',
        status: 200,
        body: JSON.stringify([
          {id: 'person-empty', name: ''},
          {id: 'person-space', name: ' \t'},
          {id: 'person-nel', name: '\u0085'},
        ]),
      };
    }
    return response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_00',
          person_id: 'person-empty',
        },
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_01',
          person_id: 'person-space',
          start: 4.5,
          end: 5,
        },
        {
          ...fixture.transcript_segments[0],
          is_user: false,
          speaker: 'SPEAKER_02',
          person_id: 'person-nel',
          start: 5,
          end: 6,
        },
      ],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).transcript,
  ).toMatchObject({
    status: 'loaded',
    segments: [
      {personName: ''},
      {personName: ' \t'},
      {personName: '\u0085'},
    ],
  });
});

test('keeps GET geolocation address and omits empty or missing locations', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: 37.7749,
        longitude: -122.4194,
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBe('123 Market St, San Francisco');
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBeUndefined();
});

test('old conversation details name Flutter GetGeolocationWidgets short address', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, Mission District, San Francisco, CA 94103',
        latitude: 37.7749,
        longitude: -122.4194,
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBe('Mission District, San Francisco');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco, CA',
        latitude: 37.7749,
        longitude: -122.4194,
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBe('123 Market St, San Francisco');
});

test('keeps GET geolocation maps open Flutter paints from required coordinates', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: 37.7749,
        longitude: -122.4194,
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    locationAddress: '123 Market St, San Francisco',
    locationMapsUrl:
      'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {latitude: 37.7749, longitude: -122.4194},
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    locationAddress: 'Unknown location',
    locationMapsUrl:
      'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: ' \t\n',
        latitude: '37.7749',
        longitude: -122.4194,
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    locationAddress: ' \t\n',
    locationMapsUrl:
      'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
  });
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '',
        latitude: 37.7749,
        longitude: -122.4194,
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject({
    locationAddress: conversationUnknownLocationCopy(),
    locationMapsUrl:
      'https://www.google.com/maps/search/?api=1&query=37.7749,-122.4194',
  });
});

test('names Flutter GetGeolocationWidgets padded GET latitude instead of remapping to Maps', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: '  37.7749  ',
        longitude: -122.4194,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: '37.7749 ',
        longitude: -122.4194,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: '\u008537.7749',
        longitude: -122.4194,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {
        address: '123 Market St, San Francisco',
        latitude: 37.7749,
        longitude: '  -122.4194  ',
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('keeps first GET apps_results content and falls back to plugins_results', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [
        {content: ' \t'},
        {content: 'App wrote this recap', app_id: 'notes'},
      ],
      plugins_results: [{content: 'Legacy plugin recap', plugin_id: 'old'}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBe('App wrote this recap');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      plugins_results: [{content: 'Legacy plugin recap'}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBe('Legacy plugin recap');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [],
      plugins_results: [{content: 'Legacy plugin recap'}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBe('Legacy plugin recap');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: ' \n'}],
      plugins_results: [{content: 'Legacy plugin recap'}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBeUndefined();
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: 'Summary'}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBeUndefined();
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummary,
  ).toBeUndefined();
});

test('keeps GET conversation apps_results when more than 1000', async () => {
  const apps_results = Array.from({length: 1001}, (_, index) => ({
    content: index === 1000 ? 'App wrote this recap' : ' \t',
  }));
  mockRequest.mockResolvedValue(response({...fixture, apps_results}));
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.appSummary).toBe('App wrote this recap');
});

test('keeps GET conversation plugins_results when more than 1000', async () => {
  const plugins_results = Array.from({length: 1001}, (_, index) => ({
    content: index === 1000 ? 'Legacy plugin recap' : ' \t',
  }));
  mockRequest.mockResolvedValue(response({...fixture, plugins_results}));
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.appSummary).toBe('Legacy plugin recap');
});

test('names Flutter AppResultDetailWidget empty GET names without Unknown App', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: ' \t',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: ' \t',
    }),
  );
});

test('names Flutter AppResultDetailWidget empty GET descriptions', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          description: ' \t',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: 'Notes',
      appSummaryDescription: ' \t',
    }),
  );
});

test('names GET apps_results app when catalog resolves and Unknown App when it misses', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          description: 'Saves notes from calls',
          image: 'https://cdn.example.test/notes.png',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [
        {
          content: 'App wrote this recap',
          plugin_id: 'notes',
          app_id: 'other',
        },
      ],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: 'Notes',
      appSummaryDescription: 'Saves notes from calls',
      appSummaryImageUri: 'https://cdn.example.test/notes.png',
    }),
  );
  expect(mockRequest).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/apps/notes',
  });
  expect(
    mockRequest.mock.calls.some(call => call[0].path === '/v1/apps/other'),
  ).toBe(false);
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {id: 'app', status: 404, body: '{}'};
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  const unresolved = await loadLegacyConversationDetail(backend, fixture.id);
  expect(unresolved.appSummary).toBe('App wrote this recap');
  expect(unresolved.appSummaryName).toBe(conversationUnknownAppCopy());
  expect(unresolved.appSummaryDescription).toBeUndefined();
  expect(unresolved.appSummaryImageUri).toBeUndefined();
  expect(unresolved.appsError).toBeUndefined();
  mockRequest.mockImplementation(async () =>
    response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 1}],
    }),
  );
  const malformedId = await loadLegacyConversationDetail(backend, fixture.id);
  expect(malformedId.appSummary).toBe('App wrote this recap');
  expect(malformedId.appSummaryName).toBeUndefined();
  mockRequest.mockReset().mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap'}],
    }),
  );
  await loadLegacyConversationDetail(backend, fixture.id);
  expect(mockRequest).toHaveBeenCalledTimes(1);
});

test('names Flutter AppResultDetailWidget padded GET app_id instead of remapping to a catalog name', async () => {
  const catalog = async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  };
  mockRequest.mockImplementation(catalog);
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: 'Notes',
    }),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (typeof request.path === 'string' && request.path.startsWith('/v1/apps/')) {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: '  notes  '}],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: conversationUnknownAppCopy(),
    }),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (typeof request.path === 'string' && request.path.startsWith('/v1/apps/')) {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes '}],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationUnknownAppCopy());
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (typeof request.path === 'string' && request.path.startsWith('/v1/apps/')) {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [
        {content: 'App wrote this recap', app_id: '\u0085notes'},
      ],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationUnknownAppCopy());
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (typeof request.path === 'string' && request.path.startsWith('/v1/apps/')) {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', plugin_id: '  notes  '}],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationUnknownAppCopy());
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        overview: 'Day recap notes',
      },
      apps_results: [{content: 'App wrote this recap', app_id: ' \t'}],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummary: 'App wrote this recap',
      appSummaryName: conversationUnknownAppCopy(),
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).not.toBe(conversationFirstPartySummaryCopy());
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        overview: 'Day recap notes',
      },
      apps_results: [{content: 'App wrote this recap', app_id: ''}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationUnknownAppCopy());
});

test('names Flutter AppResultDetailWidget padded GET image instead of remapping to a CDN chip', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          image: 'https://cdn.example.test/notes.png ',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      appSummaryImageUri: 'https://cdn.example.test/notes.png ',
    }),
  );
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          image: '  https://cdn.example.test/notes.png  ',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id))
      .appSummaryImageUri,
  ).toBeUndefined();
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      return {
        id: 'app',
        status: 200,
        body: JSON.stringify({
          id: 'notes',
          name: 'Notes',
          image: 'HTTPS://cdn.example.test/notes.png',
        }),
      };
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id))
      .appSummaryImageUri,
  ).toBeUndefined();
});

test('names Flutter first-party Summary when GET apps_results omits plugin_id', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        overview: 'Day recap notes',
      },
      apps_results: [{content: 'App wrote this recap'}],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      summary: 'Day recap notes',
      appSummary: 'App wrote this recap',
      appSummaryName: conversationFirstPartySummaryCopy(),
    }),
  );
  expect(mockRequest).toHaveBeenCalledTimes(1);
  mockRequest.mockReset().mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        overview: 'Day recap notes',
      },
      apps_results: [{content: 'App wrote this recap', app_id: null}],
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationFirstPartySummaryCopy());
  expect(mockRequest).toHaveBeenCalledTimes(1);
});

test('names Flutter first-party Summary when GET overview or sections have no app recap', async () => {
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationFirstPartySummaryCopy());
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        title: fixture.structured.title,
        overview: 'Day recap notes',
        sections: [],
      },
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toEqual(
    expect.objectContaining({
      summary: 'Day recap notes',
      appSummaryName: conversationFirstPartySummaryCopy(),
    }),
  );
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        title: fixture.structured.title,
        overview: '',
        sections: [{heading: 'Notes', body_markdown: 'Full notes'}],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBe(conversationFirstPartySummaryCopy());
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        title: fixture.structured.title,
        overview: ' \t\n',
        sections: [],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).appSummaryName,
  ).toBeUndefined();
});

test('names a failed GET apps catalog instead of omitting Unknown App as empty success', async () => {
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/apps/notes') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return response({
      ...fixture,
      apps_results: [{content: 'App wrote this recap', app_id: 'notes'}],
    });
  });
  const thrownApps = await loadLegacyConversationDetail(backend, fixture.id);
  expect(thrownApps.appSummary).toBe('App wrote this recap');
  expect(thrownApps.appSummaryName).toBeUndefined();
  expect(thrownApps.appSummaryImageUri).toBeUndefined();
  expect(thrownApps.appsError).toBe(desktopBackendServiceCopy);
});

test('fails closed for malformed GET apps_results or plugins_results', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: 'not-an-array',
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      apps_results: [{content: 1}],
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      plugins_results: {content: 'Legacy plugin recap'},
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('fails closed for malformed GET geolocation', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: 'not-an-object',
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {address: 1},
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {address: '123 Market St, San Francisco'},
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {latitude: true, longitude: -122.4194},
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('names Flutter ActionItemsTab empty GET descriptions', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {description: '', completed: false},
          {description: ' \t', completed: true},
          {description: '\u0085', completed: false},
          '',
          'Plain reminder',
        ],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).actionItems,
  ).toEqual([
    {description: '', completed: false},
    {description: ' \t', completed: true},
    {description: '\u0085', completed: false},
    {description: 'Plain reminder', completed: false},
  ]);
});

test('old conversation details name Flutter ServerConversation.fromJson padded GET action_items capture_confidence instead of remapping to an action chip', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {
            description: 'Call Alex',
            completed: true,
            capture_confidence: '0.9',
          },
        ],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).actionItems,
  ).toEqual([{description: 'Call Alex', completed: true}]);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {
            description: 'Call Alex',
            completed: true,
            capture_confidence: 0.9,
          },
        ],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).actionItems,
  ).toEqual([{description: 'Call Alex', completed: true}]);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        events: [
          {
            title: 'Standup',
            start: '2026-09-07T15:00:00.000Z',
            duration: '30',
          },
        ],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).title,
  ).toBe('A real conversation');
  for (const capture_confidence of [
    '  0.9  ',
    '0.9 ',
    '  0.9',
    '0.9\n',
    '\u00850.9',
  ]) {
    mockRequest.mockResolvedValue(
      response({
        ...fixture,
        structured: {
          ...fixture.structured,
          action_items: [
            {description: 'Call Alex', completed: true, capture_confidence},
          ],
        },
      }),
    );
    await expect(
      loadLegacyConversationDetail(backend, fixture.id),
    ).rejects.toMatchObject({kind: 'invalid'});
  }
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {
            description: 'Call Alex',
            completed: true,
            ownership_confidence: '  0.4  ',
          },
        ],
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {
            description: 'Call Alex',
            completed: true,
            due_at: '  2026-09-07T15:00:00.000Z  ',
          },
        ],
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        events: [
          {
            title: 'Standup',
            start: '  2026-09-07T15:00:00.000Z  ',
            duration: 30,
          },
        ],
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        events: [
          {
            title: 'Standup',
            start: '2026-09-07T15:00:00.000Z',
            duration: '  30  ',
          },
        ],
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
});

test('keeps GET action items and drops deleted rows', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items: [
          {description: 'Call Alex', completed: true},
          {description: 'Deleted task', completed: false, deleted: true},
          'Plain reminder',
        ],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).actionItems,
  ).toEqual([
    {description: 'Call Alex', completed: true},
    {description: 'Plain reminder', completed: false},
  ]);
});

test('keeps camelCase GET actionItems', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        actionItems: [{description: 'Send notes', completed: false}],
      },
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).actionItems,
  ).toEqual([{description: 'Send notes', completed: false}]);
});

test('does not fail conversation detail when stored sections or action items cannot project', async () => {
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        sections: [
          {heading: 'Notes', body_markdown: 'Full notes'},
          {heading: 'Broken', body_markdown: 5},
          'not-a-section',
        ],
        action_items: [
          {description: 'Call Alex', completed: true},
          {description: 'Bad completed', completed: 'false'},
          {description: 1, completed: false},
          'Plain reminder',
          '',
          12,
        ],
      },
    }),
  );
  const mixed = await loadLegacyConversationDetail(backend, fixture.id);
  expect(mixed.title).toBe('A real conversation');
  expect(mixed.sections).toEqual([
    {heading: 'Notes', bodyMarkdown: 'Full notes'},
  ]);
  expect(mixed.actionItems).toEqual([
    {description: 'Call Alex', completed: true},
    {description: 'Plain reminder', completed: false},
  ]);
  expect(mixed.transcript).toEqual({
    status: 'loaded',
    segments: [
      {
        text: 'Full speech beyond the summary',
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        sections: 1,
        action_items: {description: 'nope'},
      },
    }),
  );
  const omitted = await loadLegacyConversationDetail(backend, fixture.id);
  expect(omitted.title).toBe('A real conversation');
  expect(omitted.sections).toEqual([]);
  expect(omitted.actionItems).toEqual([]);
});

test('keeps GET conversation detail when a section heading, action item, or photo caption exceeds 10000', async () => {
  const heading = 'h'.repeat(10001);
  const description = 'd'.repeat(10001);
  const caption = 'p'.repeat(10001);
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        sections: [{heading, body_markdown: 'Full notes'}],
        action_items: [{description, completed: false}],
      },
      photos: [{description: caption, base64: ''}],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      title: fixture.structured.title,
      sections: [{heading, bodyMarkdown: 'Full notes'}],
      actionItems: [{description, completed: false}],
      photoCount: 1,
      photoCaptions: [caption],
    },
  );
});

test('keeps GET conversation sections when more than 1000', async () => {
  const sections = Array.from({length: 1001}, (_, index) => ({
    heading: `Note ${index}`,
    body_markdown: `Body ${index}`,
  }));
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        sections,
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.sections).toEqual(
    sections.map(section => ({
      heading: section.heading,
      bodyMarkdown: section.body_markdown,
    })),
  );
  expect(loaded.transcript).toEqual({
    status: 'loaded',
    segments: [
      {
        text: 'Full speech beyond the summary',
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
});

test('keeps GET conversation action items when more than 1000', async () => {
  const action_items = Array.from({length: 1001}, (_, index) => ({
    description: `Task ${index}`,
    completed: index % 2 === 0,
  }));
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        action_items,
      },
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.actionItems).toEqual(
    action_items.map(item => ({
      description: item.description,
      completed: item.completed,
    })),
  );
});

test('keeps GET conversation transcript_segments when more than 20000', async () => {
  const transcript_segments = Array.from({length: 20001}, (_, index) => ({
    ...fixture.transcript_segments[0],
    text: `Speech ${index}`,
  }));
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments,
    }),
  );
  const loaded = await loadLegacyConversationDetail(backend, fixture.id);
  expect(loaded.title).toBe(fixture.structured.title);
  expect(loaded.sections).toEqual([
    {heading: 'Notes', bodyMarkdown: 'Full notes'},
  ]);
  expect(loaded.transcript).toEqual({
    status: 'loaded',
    segments: transcript_segments.map(segment => ({
      text: segment.text,
      speaker: 'SPEAKER_00',
      isUser: true,
      start: 0.25,
      end: 4.5,
    })),
  });
});

test('does not fail conversation detail when stored title or overview is omitted', async () => {
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        sections: [{heading: 'Notes', body_markdown: 'Full notes'}],
      },
    }),
  );
  const omitted = await loadLegacyConversationDetail(backend, fixture.id);
  expect(omitted.title).toBe('');
  expect(omitted.summary).toBe('');
  expect(omitted.sections).toEqual([
    {heading: 'Notes', bodyMarkdown: 'Full notes'},
  ]);
  expect(omitted.transcript).toEqual({
    status: 'loaded',
    segments: [
      {
        text: 'Full speech beyond the summary',
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        title: null,
        overview: null,
      },
    }),
  );
  const nulled = await loadLegacyConversationDetail(backend, fixture.id);
  expect(nulled.title).toBe('');
  expect(nulled.summary).toBe('');
  expect(nulled.transcript).toEqual({
    status: 'loaded',
    segments: [
      {
        text: 'Full speech beyond the summary',
        speaker: 'SPEAKER_00',
        isUser: true,
        start: 0.25,
        end: 4.5,
      },
    ],
  });
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        title: 1,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
  mockRequest.mockResolvedValueOnce(
    response({
      ...fixture,
      structured: {
        ...fixture.structured,
        overview: 5,
      },
    }),
  );
  await expect(
    loadLegacyConversationDetail(backend, fixture.id),
  ).rejects.toMatchObject({kind: 'invalid'});
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
    transcript_segments: [{...fixture.transcript_segments[0], start: ''}],
  },
  {
    ...fixture,
    transcript_segments: [{...fixture.transcript_segments[0], is_user: null}],
  },
  {
    ...fixture,
    transcript_segments: [{...fixture.transcript_segments[0], speaker: 1}],
  },
  {
    ...fixture,
    transcript_segments: [
      {
        ...fixture.transcript_segments[0],
        translations: [{text: 'Hola'}],
      },
    ],
  },
  {
    ...fixture,
    transcript_segments: [
      {
        ...fixture.transcript_segments[0],
        translations: 'es',
      },
    ],
  },
  {
    ...fixture,
    transcript_segments: [
      {
        ...fixture.transcript_segments[0],
        stt_provider: 1,
      },
    ],
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
