const nock = require('nock');
const zapier = require('zapier-platform-core');

// Use this to make test calls into your app:
const App = require('../../index');
const appTester = zapier.createAppTester(App);
// read the `.env` file into the environment, if available
zapier.tools.env.inject();

const API_HOST = 'https://based-hardware--plugins-api.modal.run';

describe('triggers.on_memory_created', () => {
  beforeAll(() => nock.disableNetConnect());
  afterEach(() => nock.cleanAll());
  afterAll(() => nock.enableNetConnect());

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

  it('should include Authorization header on performSubscribe', async () => {
    const scope = nock(API_HOST, {
      reqheaders: {
        authorization: 'Bearer tok-sub-test',
        'content-type': 'application/json',
      },
    })
      .post('/zapier/trigger/subscribe', {
        target_url: 'https://hooks.zapier.com/test-target',
      })
      .query({ uid: 'u-sub-test' })
      .reply(200, { success: true });

    const bundle = {
      targetUrl: 'https://hooks.zapier.com/test-target',
      authData: { uid: 'u-sub-test', token: 'tok-sub-test' },
    };

    await appTester(
      App.triggers['on_memory_created'].operation.performSubscribe,
      bundle
    );
    expect(scope.isDone()).toBe(true);
  });

  it('should include Authorization header on performUnsubscribe', async () => {
    const scope = nock(API_HOST, {
      reqheaders: {
        authorization: 'Bearer tok-unsub-test',
        'content-type': 'application/json',
      },
    })
      .delete('/zapier/trigger/subscribe', {
        target_url: 'https://hooks.zapier.com/test-target',
      })
      .query(true)
      .reply(200, { success: true });

    const bundle = {
      targetUrl: 'https://hooks.zapier.com/test-target',
      authData: { uid: 'u-sub-test', token: 'tok-unsub-test' },
    };

    await appTester(
      App.triggers['on_memory_created'].operation.performUnsubscribe,
      bundle
    );
    expect(scope.isDone()).toBe(true);
  });
});
