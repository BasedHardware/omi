module.exports = {
  type: 'custom',
  test: {
    headers: {
      'X-UID': '{{bundle.authData.uid}}',
      Authorization: 'Bearer {{bundle.authData.token}}',
    },
    removeMissingValuesFrom: { body: false, params: false },
    url: 'https://based-hardware--plugins-api.modal.run/zapier/me',
  },
  fields: [
    {
      helpText:
        'You can find the Secret Key in the Omi App under Explore > Apps > Zapier > Integration Instructions',
      computed: false,
      key: 'uid',
      required: true,
      label: 'Secret Key',
      type: 'password',
    },
    {
      helpText:
        'Integration token provisioned alongside the Secret Key in the Omi App under Explore > Apps > Zapier > Integration Instructions. Required once the backend enables authenticated Zapier endpoints.',
      computed: false,
      key: 'token',
      required: false,
      label: 'Integration Token',
      type: 'password',
    },
  ],
  customConfig: {},
};
