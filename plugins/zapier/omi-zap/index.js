const authentication = require('./authentication');
const onMemoryCreatedTrigger = require('./triggers/on_memory_created.js');
const createMemoryCreate = require('./creates/create_memory.js');

module.exports = {
  version: require('./package.json').version,
  platformVersion: require('zapier-platform-core').version,
  authentication: authentication,
  requestTemplate: {
    params: { uid: '{{bundle.authData.uid}}' },
    headers: { 'X-UID': '{{bundle.authData.uid}}' },
  },
  triggers: { [onMemoryCreatedTrigger.key]: onMemoryCreatedTrigger },
  creates: { [createMemoryCreate.key]: createMemoryCreate },
};
