module.exports = {
  type: 'custom',
  test: {
    headers: { 'X-UID': '{{bundle.authData.uid}}' },
    removeMissingValuesFrom: { body: false, params: false },
    url: 'https://based-hardware--plugins-api.modal.run/zapier/me',
  },
  fields: [
    {
      helpText:
        'You can find the Secret Key in the Friend App under Settings > Plugins > Integration > Zapier > Integration Instructions',
      computed: false,
      key: 'uid',
      required: true,
      label: 'Secret Key',
      type: 'password',
    },
  ],
  customConfig: {},
};
