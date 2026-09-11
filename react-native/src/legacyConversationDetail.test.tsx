import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  conversationPhotoAnalyzingCopy,
  conversationPhotoDiscardedCopy,
  desktopBackendServiceCopy,
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
    attendees: ['Alex Chen', 'sam@example.com'],
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
  expect(untitled.calendarEvent).not.toHaveProperty('title');
  expect(untitled.calendarEvent?.attendees).toEqual([]);
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).calendarEvent,
  ).toBeUndefined();
});

test('names GET transcript translations and omits empty or missing lists', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      transcript_segments: [
        {
          ...fixture.transcript_segments[0],
          translations: [
            {lang: 'es', text: 'Hola alli'},
            {lang: 'fr', text: ' \t'},
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
        translations: ['Hola alli'],
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

test('names GET transcript stt_provider without inventing Flutter Omi for unknown', async () => {
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
        sttProvider: 'whisper-cloudflare',
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
      },
    ],
  });
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
        {description: 'Whiteboard notes'},
        {description: ' \t'},
        {id: 'three'},
      ],
    }),
  );
  expect(await loadLegacyConversationDetail(backend, fixture.id)).toMatchObject(
    {
      photoCount: 3,
      photoCaptions: ['Whiteboard notes', conversationPhotoAnalyzingCopy()],
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

test('names GET discarded photos and photos still analyzing', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      photos: [
        {description: 'Whiteboard notes'},
        {description: 'ignored caption', discarded: true},
        {id: 'pending'},
        {description: '   ', discarded: false},
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
      ],
    },
  );
});

test('keeps GET photo base64 inline and omits empty, invalid, or storage-only photos', async () => {
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
        },
      ],
    }),
  );
  const value = await loadLegacyConversationDetail(backend, fixture.id);
  expect(value).toMatchObject({
    photoCount: 5,
    photoCaptions: [
      'Whiteboard notes',
      'No bytes',
      'Whitespace',
      'Corrupt',
      'Stored elsewhere',
    ],
    photoRows: [
      {
        caption: 'Whiteboard notes',
        imageUri: `data:image/png;base64,${png}`,
      },
      {caption: 'No bytes'},
      {caption: 'Whitespace'},
      {caption: 'Corrupt'},
      {caption: 'Stored elsewhere'},
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
});

test('names GET folder name when folders resolve and omits otherwise', async () => {
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
    }),
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
  ).toBeUndefined();
  mockRequest.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/folders') {
      return {id: 'folders', status: 500, body: '[]'};
    }
    return response({...fixture, folder_id: 'folder-work'});
  });
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).folderName,
  ).toBeUndefined();
  mockRequest.mockReset().mockResolvedValue(response(fixture));
  await loadLegacyConversationDetail(backend, fixture.id);
  expect(mockRequest).toHaveBeenCalledTimes(1);
});

test('keeps GET external_data text and omits empty or missing integration copy', async () => {
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
  ).toBeUndefined();
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

test('keeps GET geolocation address and omits empty or missing locations', async () => {
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {address: '123 Market St, San Francisco'},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBe('123 Market St, San Francisco');
  mockRequest.mockResolvedValue(
    response({
      ...fixture,
      geolocation: {address: ' \t\n'},
    }),
  );
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBeUndefined();
  mockRequest.mockResolvedValue(response(fixture));
  expect(
    (await loadLegacyConversationDetail(backend, fixture.id)).locationAddress,
  ).toBeUndefined();
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

test('names GET apps_results app when catalog resolves and omits Unknown App', async () => {
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
  expect(unresolved.appSummaryName).toBeUndefined();
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
  {
    ...fixture,
    structured: {
      ...fixture.structured,
      action_items: [{description: 'Call Alex', completed: 'false'}],
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
