module.exports = {
  type: 'custom',
  test: {
    headers: { 'X-UID': '{{bundle.authData.uid}}' },
    removeMissingValuesFrom: { body: false, params: false },
    url: ' https://omi-plug-zpqkexos-zapier.thinhcto.com/zapier/me',
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
