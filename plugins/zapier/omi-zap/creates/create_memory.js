const body = async (z, bundle) => {
  {
    {
      bundle.inputData.source;
    }
  }
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
