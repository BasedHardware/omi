import {loadOmiPeopleNames, parseOmiPeopleNames} from './legacyOmiPeople';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET people names and omits empty names', () => {
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id: 'person-alex', name: 'Alex Chen'},
      {id: 'person-empty', name: ' \t'},
    ]),
  );
  expect(names.get('person-alex')).toBe('Alex Chen');
  expect(names.has('person-empty')).toBe(false);
});

test('keeps GET people names when a person id exceeds 256', () => {
  const id = 'p'.repeat(257);
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id, name: 'Alex Chen'},
      {id: 'person-neighbor', name: 'Jordan Lee'},
    ]),
  );
  expect(names.get(id)).toBe('Alex Chen');
  expect(names.get('person-neighbor')).toBe('Jordan Lee');
});

test('fails closed for malformed GET people', () => {
  expect(() =>
    parseOmiPeopleNames(JSON.stringify({id: 'person-alex'})),
  ).toThrow();
  expect(() =>
    parseOmiPeopleNames(JSON.stringify([{id: 'person-alex', name: 1}])),
  ).toThrow();
  expect(() =>
    parseOmiPeopleNames(
      JSON.stringify([
        {id: 'person-alex', name: 'Alex Chen'},
        {id: 'person-alex', name: 'Dup'},
      ]),
    ),
  ).toThrow();
});

test('loadOmiPeopleNames names resolved GET people and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'people',
    status: 200,
    body: JSON.stringify([{id: 'person-alex', name: 'Alex Chen'}]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect((await loadOmiPeopleNames(backend)).get('person-alex')).toBe(
    'Alex Chen',
  );
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/people?include_speech_samples=false',
  });
  request.mockResolvedValueOnce({id: 'people', status: 500, body: '[]'});
  expect((await loadOmiPeopleNames(backend)).size).toBe(0);
  request.mockResolvedValueOnce({id: 'people', status: 200, body: '{'});
  expect((await loadOmiPeopleNames(backend)).size).toBe(0);
});
