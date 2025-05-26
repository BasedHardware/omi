const perform = async (z, bundle) => {
  return [bundle.cleanedRequest];
};

module.exports = {
  operation: {
    perform: perform,
    type: 'hook',
    performUnsubscribe: {
      body: { target_url: '{{bundle.targetUrl}}' },
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      method: 'DELETE',
      removeMissingValuesFrom: { body: false, params: false },
      url: 'https://based-hardware--plugins-api.modal.run/zapier/trigger/subscribe',
    },
    performSubscribe: {
      body: { target_url: '{{bundle.targetUrl}}' },
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      method: 'POST',
      params: { uid: '{{bundle.authData.uid}}' },
      removeMissingValuesFrom: { body: false, params: false },
      url: 'https://based-hardware--plugins-api.modal.run/zapier/trigger/subscribe',
    },
    sample: {
      icon: { type: 'emoji', emoji: '🥳' },
      title: 'string',
      speakers: 0,
      category: 'other',
      duration: 0,
      overview: 'string',
    },
    outputFields: [
      { key: 'icon__type' },
      { key: 'icon__emoji' },
      { key: 'title', type: 'string' },
      { key: 'speakers', type: 'number' },
      { key: 'category' },
      { key: 'duration', type: 'number' },
      { key: 'overview' },
    ],
  },
  display: {
    description: 'Trigger when a new memory is created.',
    hidden: false,
    label: 'New Memory Created',
  },
  key: 'on_memory_created',
  noun: 'Memory',
};
