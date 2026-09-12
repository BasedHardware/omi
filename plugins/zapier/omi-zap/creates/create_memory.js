// Creates a Memory in the Omi system.
//
// Bug fix (2026-09-12):
// The previous `body` function was declared `async` but never returned a value,
// so zapier-platform-core awaited it, received `undefined`, and sent an empty
// JSON body — every Create Memory invocation 422'd at
// https://based-hardware--plugins-api.modal.run/zapier/action/memories.
//
// This rewrite:
//   - Declares `body` synchronously (it does not need `await`).
//   - Returns a plain object matching the backend contract enforced by
//     `ZapierActionCreateConversation` (text + source are required).
//   - Passes through every optional field the existing inputFields already
//     declares so that the removeMissingValuesFrom filter still works.

const body = (z, bundle) => {
  const inputData = bundle.inputData || {};

  // Required by the backend
  const payload = {
    text: inputData.text,
    source: inputData.source || 'audio_transcript',
  };

  // Pass through optional scalar fields when present.
  if (inputData.language !== undefined && inputData.language !== null) {
    payload.language = inputData.language;
  }
  if (inputData.started_at) {
    payload.started_at = inputData.started_at;
  }
  if (inputData.finished_at) {
    payload.finished_at = inputData.finished_at;
  }

  // Nested geolocation — only include when at least one child is present.
  if (
    inputData.geolocation &&
    typeof inputData.geolocation === 'object' &&
    Object.values(inputData.geolocation).some(
      (v) => v !== undefined && v !== null && v !== '',
    )
  ) {
    payload.geolocation = inputData.geolocation;
  }

  return payload;
};

module.exports = {
  display: {
    description: 'Creates a Memory in the system',
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
          'It could be your audio transcript, podcast, diary, or anything else related to your memory that you want your Omi to know.',
        required: true,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'source',
        label: 'Is this an audio transcript or just text?',
        type: 'string',
        helpText: 'This will help Omi get to know you better.',
        default: 'audio_transcript',
        choices: ['audio_transcript', 'other_text'],
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'language',
        label: 'Language',
        type: 'string',
        default: 'en',
        required: true,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'started_at',
        label: 'Set custom start time',
        type: 'datetime',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'finished_at',
        label: 'Set custom finish time',
        type: 'datetime',
        required: false,
        list: false,
        altersDynamicFields: false,
      },
      {
        key: 'geolocation',
        children: [
          {
            key: 'google_place_id',
            label: 'Google Place ID',
            type: 'string',
            required: false,
            list: false,
            altersDynamicFields: false,
          },
          {
            key: 'latitude',
            label: 'Latitude',
            type: 'number',
            required: false,
            list: false,
            altersDynamicFields: false,
          },
          {
            key: 'longitude',
            label: 'Longitude',
            type: 'number',
            required: false,
            list: false,
            altersDynamicFields: false,
          },
          {
            key: 'address',
            label: 'Address',
            type: 'string',
            required: false,
            list: false,
            altersDynamicFields: false,
          },
          {
            key: 'location_type',
            label: 'Location Type',
            type: 'string',
            required: false,
            list: false,
            altersDynamicFields: false,
          },
        ],
        label: 'Geolocation',
        required: false,
        altersDynamicFields: false,
      },
    ],
    perform: {
      body: body,
      method: 'POST',
      removeMissingValuesFrom: { body: true, params: true },
      url: 'https://based-hardware--plugins-api.modal.run/zapier/action/memories',
    },
  },
};