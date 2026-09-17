import {parseTrainingOptIn} from './desktopCloudClient';

test('names Flutter TrainingDataOptInResponse fromJson type-wrong GET status instead of remapping to opted-in', () => {
  const optedIn = {opted_in: true};
  const neighbor = {opted_in: false};
  expect(parseTrainingOptIn({...optedIn, status: 'ok'}, 'Training opt-in response')).toBe(
    true,
  );
  expect(parseTrainingOptIn(optedIn, 'Training opt-in response')).toBe(true);
  expect(parseTrainingOptIn({...optedIn, status: null}, 'Training opt-in response')).toBe(
    true,
  );
  expect(parseTrainingOptIn({...optedIn, status: ''}, 'Training opt-in response')).toBe(
    true,
  );
  expect(
    parseTrainingOptIn({...optedIn, extra: 1}, 'Training opt-in response'),
  ).toBe(true);
  expect(parseTrainingOptIn(neighbor, 'Training opt-in response')).toBe(false);
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseTrainingOptIn({...optedIn, status: extra}, 'Training opt-in response'),
    ).toThrow('Training opt-in response is malformed');
  }
});
