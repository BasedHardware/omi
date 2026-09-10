import {
  loadOmiIntegrations,
  parseOmiIntegration,
} from './legacyOmiIntegrations';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET connected integrations and omits disconnected', () => {
  expect(
    parseOmiIntegration(
      JSON.stringify({app_key: 'gmail', connected: true}),
      'gmail',
    ),
  ).toEqual({key: 'gmail', name: 'Gmail'});
  expect(
    parseOmiIntegration(
      JSON.stringify({app_key: 'google_calendar', connected: false}),
      'google_calendar',
    ),
  ).toBeNull();
  expect(
    parseOmiIntegration(
      JSON.stringify({app_key: 'apple_health', connected: true}),
      'apple_health',
    ),
  ).toEqual({key: 'apple_health', name: 'Apple Health'});
  expect(
    parseOmiIntegration(
      JSON.stringify({
        app_key: 'gmail',
        connected: true,
        details: {access_token: 'secret'},
      }),
      'gmail',
    ),
  ).toEqual({key: 'gmail', name: 'Gmail'});
});

test('fails closed for malformed GET integrations', () => {
  expect(() => parseOmiIntegration(JSON.stringify([]), 'gmail')).toThrow();
  expect(() =>
    parseOmiIntegration(JSON.stringify({connected: true}), 'gmail'),
  ).toThrow();
  expect(() =>
    parseOmiIntegration(
      JSON.stringify({app_key: 'gmail', connected: 'true'}),
      'gmail',
    ),
  ).toThrow();
  expect(() =>
    parseOmiIntegration(
      JSON.stringify({app_key: 'google_calendar', connected: true}),
      'gmail',
    ),
  ).toThrow();
});

test('loadOmiIntegrations names connected GET rows and omits failures', async () => {
  const request = jest.fn(async (input: {path: string}) => {
    if (input.path === '/v1/integrations/gmail') {
      return {
        id: 'integrations',
        status: 200,
        body: JSON.stringify({app_key: 'gmail', connected: true}),
      };
    }
    if (input.path === '/v1/integrations/google_calendar') {
      return {
        id: 'integrations',
        status: 200,
        body: JSON.stringify({app_key: 'google_calendar', connected: false}),
      };
    }
    if (input.path === '/v1/integrations/apple_health') {
      return {id: 'integrations', status: 404, body: '{}'};
    }
    return {id: 'integrations', status: 404, body: null};
  });
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiIntegrations(backend)).toEqual([
    {key: 'gmail', name: 'Gmail'},
  ]);
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/integrations/gmail',
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/integrations/google_calendar',
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/integrations/apple_health',
  });
  expect(
    request.mock.calls.some(
      call => call[0].method === 'PUT' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    request.mock.calls.some(
      call =>
        typeof call[0].path === 'string' && call[0].path.includes('oauth-url'),
    ),
  ).toBe(false);
  request.mockImplementation(async (input: {path: string}) => ({
    id: 'integrations',
    status: 200,
    body: JSON.stringify({
      app_key: input.path.slice('/v1/integrations/'.length),
      connected: true,
    }),
  }));
  expect(await loadOmiIntegrations(backend)).toEqual([
    {key: 'apple_health', name: 'Apple Health'},
    {key: 'google_calendar', name: 'Google Calendar'},
    {key: 'gmail', name: 'Gmail'},
  ]);
});
