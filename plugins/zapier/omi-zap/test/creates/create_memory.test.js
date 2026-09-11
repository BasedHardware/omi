const nock = require('nock');
const zapier = require('zapier-platform-core');

// Use this to make test calls into your app:
const App = require('../../index');
const appTester = zapier.createAppTester(App);
// read the `.env` file into the environment, if available
zapier.tools.env.inject();

const API_HOST = 'https://based-hardware--plugins-api.modal.run';

// Intercepts one POST to the create-memory endpoint and exposes the parsed
// JSON body so assertions run after the call, not inside nock's predicate.
const mockCreateMemory = () => {
  let postedBody;
  const scope = nock(API_HOST)
    .post('/zapier/action/memories', (body) => {
      postedBody = body;
      return true;
    })
    .query({ uid: 'u-test' })
    .reply(200, { message: 'Your memories are synced with Omi.' });
  return { scope, getPostedBody: () => postedBody };
};

const runCreateMemory = (inputData) =>
  appTester(App.creates['create_memory'].operation.perform, {
    authData: { uid: 'u-test' },
    inputData,
  });

describe('creates.create_memory', () => {
  afterEach(() => nock.cleanAll());

  it('sends the input fields as the request body', async () => {
    // Regression: `body` was an async function with no return, so the POST went
    // out empty and the API rejected every Zap run with a 422. Expected field
    // names and the required/optional split come from
    // ZapierActionCreateConversation in plugins/zapier/models.py.
    const { scope, getPostedBody } = mockCreateMemory();

    const results = await runCreateMemory({
      text: 'Ship the report',
      source: 'other_text',
      language: 'en',
      started_at: '2026-09-11T10:00:00Z',
      finished_at: '2026-09-11T11:00:00Z',
      geolocation: {
        latitude: 37.422,
        longitude: -122.084,
        address: '1600 Amphitheatre Pkwy',
      },
    });

    expect(scope.isDone()).toBe(true);
    expect(results).toBeDefined();
    expect(getPostedBody()).toEqual({
      text: 'Ship the report',
      source: 'other_text',
      language: 'en',
      started_at: '2026-09-11T10:00:00Z',
      finished_at: '2026-09-11T11:00:00Z',
      geolocation: {
        latitude: 37.422,
        longitude: -122.084,
        address: '1600 Amphitheatre Pkwy',
      },
    });
  });

  it('omits optional fields that were not supplied', async () => {
    const { scope, getPostedBody } = mockCreateMemory();

    await runCreateMemory({
      text: 'Hello',
      source: 'other_text',
      language: 'en',
    });

    expect(scope.isDone()).toBe(true);
    expect(getPostedBody()).toEqual({
      text: 'Hello',
      source: 'other_text',
      language: 'en',
    });
  });
});
