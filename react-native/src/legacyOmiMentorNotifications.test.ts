import {
  loadOmiMentorNotificationSettings,
  parseOmiMentorNotificationSettings,
} from './legacyOmiMentorNotifications';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET mentor notification frequency without a Balanced default', () => {
  expect(
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: 0})),
  ).toEqual({frequency: 0});
  expect(
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: 5})),
  ).toEqual({frequency: 5});
});

test('does not omit mentor notification settings when stored frequency is an integer string', () => {
  expect(
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: '3'})),
  ).toEqual({frequency: 3});
});

test('does not omit GET mentor notification settings when frequency is outside 0-5', () => {
  expect(
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: 6})),
  ).toEqual({frequency: 6});
  expect(
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: -1})),
  ).toEqual({frequency: -1});
});

test('fails closed for malformed GET mentor notification settings', () => {
  expect(() =>
    parseOmiMentorNotificationSettings(JSON.stringify([])),
  ).toThrow();
  expect(() =>
    parseOmiMentorNotificationSettings(JSON.stringify({})),
  ).toThrow();
  expect(() =>
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: 1.5})),
  ).toThrow();
  expect(() =>
    parseOmiMentorNotificationSettings(JSON.stringify({frequency: '3.0'})),
  ).toThrow();
});

test('loadOmiMentorNotificationSettings names resolved GET frequency and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'mentor',
    status: 200,
    body: JSON.stringify({frequency: 4}),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiMentorNotificationSettings(backend)).toEqual({
    frequency: 4,
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/mentor-notification-settings',
  });
  request.mockResolvedValueOnce({id: 'mentor', status: 404, body: '{}'});
  expect(await loadOmiMentorNotificationSettings(backend)).toBeNull();
  request.mockResolvedValueOnce({id: 'mentor', status: 200, body: '{'});
  expect(await loadOmiMentorNotificationSettings(backend)).toBeNull();
});
