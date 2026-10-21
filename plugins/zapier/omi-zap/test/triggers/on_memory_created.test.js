const zapier = require('zapier-platform-core');

// Use this to make test calls into your app:
const App = require('../../index');
const appTester = zapier.createAppTester(App);
// read the `.env` file into the environment, if available
zapier.tools.env.inject();

describe('triggers.on_memory_created', () => {
  it('should run', async () => {
    const bundle = {
      inputData: {},
      cleanedRequest: {
        id: 123,
        title: 'Test Memory',
      },
    };

    const results = await appTester(
      App.triggers['on_memory_created'].operation.perform,
      bundle
    );
    expect(results).toBeDefined();
    expect(results.length).toBe(1);
    expect(results[0]).toEqual(bundle.cleanedRequest);
  });
});
