const nock = require('nock');
const zapier = require('zapier-platform-core');

// Use this to make test calls into your app:
const App = require('../../index');
const appTester = zapier.createAppTester(App);
// read the `.env` file into the environment, if available
zapier.tools.env.inject();

const API_HOST = 'https://based-hardware--plugins-api.modal.run';

describe('creates.create_memory', () => {
  afterEach(() => nock.cleanAll());

  it('sends the input fields as the request body', async () => {
    // Regression: `body` was an async function with no return, so the POST went
    // out empty and the API rejected every Zap run with a 422. The request
    // shorthand must map each declared input field onto the backend contract
    // (ZapierActionCreateConversation in plugins/zapier/models.py).
    const scope = nock(API_HOST)
      .post('/zapier/action/memories', (body) => {
        expect(body.text).toBe('Ship the report');
        expect(body.source).toBe('other_text');
        expect(body.language).toBe('en');
        expect(body.started_at).toBe('2026-09-11T10:00:00Z');
        return true;
      })
      .query({ uid: 'u-test' })
      .reply(200, { message: 'Your memories are synced with Omi.' });

    const results = await appTester(
      App.creates['create_memory'].operation.perform,
      {
        authData: { uid: 'u-test' },
        inputData: {
          text: 'Ship the report',
          source: 'other_text',
          language: 'en',
          started_at: '2026-09-11T10:00:00Z',
        },
      }
    );

    expect(scope.isDone()).toBe(true);
    expect(results).toBeDefined();
  });

  it('omits optional fields that were not supplied', async () => {
    const scope = nock(API_HOST)
      .post('/zapier/action/memories', (body) => {
        expect(body.text).toBe('Hello');
        expect('started_at' in body).toBe(false);
        expect('finished_at' in body).toBe(false);
        expect('geolocation' in body).toBe(false);
        return true;
      })
      .query({ uid: 'u-test' })
      .reply(200, { message: 'ok' });

    await appTester(App.creates['create_memory'].operation.perform, {
      authData: { uid: 'u-test' },
      inputData: { text: 'Hello', source: 'other_text', language: 'en' },
    });

    expect(scope.isDone()).toBe(true);
  });
});
