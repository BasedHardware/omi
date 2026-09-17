// Creates a Memory in the Omi system.
//
// Bug fix (2026-09-12):
// The previous `body` function was declared `async` but never returned a value,
// so zapier-platform-core awaited it, received `undefined`, and sent an empty
// JSON body — every Create Memory invocation 422'd at the Zapier action endpoint.
//
// This rewrite:
//   - Declares `body` synchronously (no `await` needed).
//   - Returns a plain object matching the backend contract (see plugins/zapier/models.py:
//     required `text` + `source`; optional `language`, `started_at`, `finished_at`,
//     `geolocation`; `audio_transcript` is a valid `ExternalIntegrationConversationSource`).
//   - Drops the no-op `try/catch` that swallowed every error and made debugging impossible.
//
// The minimal repro is: any Create Memory Zap → 422 "request body is empty".
// After this change the same Zap returns 200 with a Memory id.

module.exports = {
  display: {
    description: 'Creates a Memory in the Omi system',
    hidden: false,
    label: 'Create Memory',
  },
  key: 'create_memory',
  noun: 'Memory',
  operation: {
    inputFields: [
      {
        key: 'text',
        label: 'Omi Memory',
        type: 'string',
        helpText:
          'It could be your audio transcript, podcast, diary, or anything else related to your memory.',
        required: true,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'source',
        label: 'Source',
        type: 'string',
        helpText:
          'Optional. Defaults to "zapier" if not provided. Allowed values: any ExternalIntegrationConversationSource enum member (see plugins/zapier/models.py) — including `audio_transcript`, `other`, `workflow`, etc.',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'language',
        label: 'Language',
        type: 'string',
        helpText: 'Optional ISO-639-1 code (e.g. `en`, `es`).',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'started_at',
        label: 'Started at',
        type: 'string',
        helpText: 'Optional ISO-8601 timestamp for the conversation start.',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'finished_at',
        label: 'Finished at',
        type: 'string',
        helpText: 'Optional ISO-8601 timestamp for the conversation end.',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'geolocation',
        label: 'Geolocation',
        type: 'string',
        helpText: 'Optional lat,lng pair (e.g. "37.7749,-122.4194").',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
    ],

    perform: async (z, bundle) => {
      // Mirror the input fields into the body shape the backend expects.
      const body = {
        text: bundle.inputData.text,
        source: bundle.inputData.source || 'zapier',
      };

      if (bundle.inputData.language) body.language = bundle.inputData.language;
      if (bundle.inputData.started_at) body.started_at = bundle.inputData.started_at;
      if (bundle.inputData.finished_at) body.finished_at = bundle.inputData.finished_at;
      if (bundle.inputData.geolocation) body.geolocation = bundle.inputData.geolocation;

      const response = await z.request({
        url: 'https://based-hardware--plugins-api.modal.run/zapier/action/memories',
        method: 'POST',
        body,
      });

      return response.json;
    },

    sample: {
      id: 'mem_01HXXXXXXXXXXXXXXXXXXXXXXX',
      text: 'Sample memory content.',
      created_at: '2026-09-12T00:00:00.000Z',
    },

    outputFields: [
      { key: 'id', label: 'Memory ID', type: 'string' },
      { key: 'text', label: 'Memory Text', type: 'string' },
      { key: 'created_at', label: 'Created At', type: 'string' },
    ],
  },
};
