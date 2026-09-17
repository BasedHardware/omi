import {loadOmiPeopleNames, parseOmiPeopleNames} from './legacyOmiPeople';
import type {OmiBackend} from './omiNativeTypes';

test('names Flutter People.build empty GET names instead of omitting them', () => {
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id: 'person-alex', name: 'Alex Chen'},
      {id: 'person-empty', name: ' \t'},
      {id: 'person-next', name: '\u0085'},
      {id: 'person-blank', name: ''},
    ]),
  );
  expect(names.get('person-alex')).toBe('Alex Chen');
  expect(names.get('person-empty')).toBe(' \t');
  expect(names.get('person-next')).toBe('\u0085');
  expect(names.get('person-blank')).toBe('');
});

test('names Flutter People.build empty GET ids instead of omitting them', () => {
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id: 'person-alex', name: 'Alex Chen'},
      {id: ' \t', name: 'Whitespace id'},
      {id: '\u0085', name: 'Next line id'},
      {id: '', name: 'Blank id'},
      {id: '  padded  ', name: 'Padded id'},
    ]),
  );
  expect(names.get('person-alex')).toBe('Alex Chen');
  expect(names.get(' \t')).toBe('Whitespace id');
  expect(names.get('\u0085')).toBe('Next line id');
  expect(names.get('')).toBe('Blank id');
  expect(names.get('  padded  ')).toBe('Padded id');
});

test('old people names name Flutter Person.fromGenerated padded GET created_at instead of remapping to a person chip', () => {
  expect(
    parseOmiPeopleNames(
      JSON.stringify([
        {
          id: 'person-alex',
          name: 'Alex Chen',
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          speech_samples_version: '3',
        },
        {
          id: 'person-json',
          name: 'Jordan Lee',
          created_at: '2026-09-07T00:00:00.000Z',
          updated_at: '2026-09-07T00:00:00.000Z',
          speech_samples_version: 3,
        },
        {id: 'person-kept', name: 'Neighbor'},
      ]),
    ),
  ).toEqual(
    new Map([
      ['person-alex', 'Alex Chen'],
      ['person-json', 'Jordan Lee'],
      ['person-kept', 'Neighbor'],
    ]),
  );
  expect(
    parseOmiPeopleNames(
      JSON.stringify([
        {id: 'person-alex', name: 'Alex Chen'},
        {id: 'person-kept', name: 'Neighbor'},
      ]),
    ),
  ).toEqual(
    new Map([
      ['person-alex', 'Alex Chen'],
      ['person-kept', 'Neighbor'],
    ]),
  );
  expect(
    parseOmiPeopleNames(
      JSON.stringify([
        {
          id: 'person-alex',
          name: 'Alex Chen',
          created_at: null,
          updated_at: null,
          speech_samples_version: null,
        },
        {id: 'person-kept', name: 'Neighbor'},
      ]),
    ),
  ).toEqual(
    new Map([
      ['person-alex', 'Alex Chen'],
      ['person-kept', 'Neighbor'],
    ]),
  );
  for (const created_at of [
    '  2026-09-07T00:00:00.000Z  ',
    '2026-09-07T00:00:00.000Z ',
    '  2026-09-07T00:00:00.000Z',
    '2026-09-07T00:00:00.000Z\n',
    '\u00852026-09-07T00:00:00.000Z',
  ]) {
    expect(() =>
      parseOmiPeopleNames(
        JSON.stringify([
          {id: 'person-alex', name: 'Alex Chen', created_at},
          {id: 'person-kept', name: 'Neighbor'},
        ]),
      ),
    ).toThrow('Omi people are malformed');
  }
  expect(() =>
    parseOmiPeopleNames(
      JSON.stringify([
        {
          id: 'person-alex',
          name: 'Alex Chen',
          updated_at: '  2026-09-07T00:00:00.000Z  ',
        },
        {id: 'person-kept', name: 'Neighbor'},
      ]),
    ),
  ).toThrow('Omi people are malformed');
  expect(() =>
    parseOmiPeopleNames(
      JSON.stringify([
        {
          id: 'person-alex',
          name: 'Alex Chen',
          speech_samples_version: '  3  ',
        },
        {id: 'person-kept', name: 'Neighbor'},
      ]),
    ),
  ).toThrow('Omi people are malformed');
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

test('keeps GET people names when a person id exceeds 10000', () => {
  const id = 'p'.repeat(10001);
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id, name: 'Alex Chen'},
      {id: 'person-neighbor', name: 'Jordan Lee'},
    ]),
  );
  expect(names.get(id)).toBe('Alex Chen');
  expect(names.get('person-neighbor')).toBe('Jordan Lee');
});

test('fails closed when a person id exceeds 1000000', () => {
  expect(() =>
    parseOmiPeopleNames(
      JSON.stringify([
        {id: 'p'.repeat(1_000_001), name: 'Alex Chen'},
        {id: 'person-neighbor', name: 'Jordan Lee'},
      ]),
    ),
  ).toThrow();
});

test('keeps GET people names when a name exceeds 10000', () => {
  const name = 'A'.repeat(10001);
  const names = parseOmiPeopleNames(
    JSON.stringify([
      {id: 'person-long', name},
      {id: 'person-neighbor', name: 'Jordan Lee'},
    ]),
  );
  expect(names.get('person-long')).toBe(name);
  expect(names.get('person-neighbor')).toBe('Jordan Lee');
});

test('does not omit neighboring GET people names when the catalogue exceeds 1000', () => {
  const rows = Array.from({length: 1001}, (_, index) => ({
    id: `person-${index}`,
    name: `Person ${index}`,
  }));
  const names = parseOmiPeopleNames(JSON.stringify(rows));
  expect(names.get('person-0')).toBe('Person 0');
  expect(names.get('person-1000')).toBe('Person 1000');
  expect(names.size).toBe(1001);
});

test('fails closed for malformed GET people', () => {
  expect(() =>
    parseOmiPeopleNames(JSON.stringify({id: 'person-alex'})),
  ).toThrow();
  expect(() =>
    parseOmiPeopleNames(JSON.stringify([{id: 'person-alex', name: 1}])),
  ).toThrow();
  expect(() =>
    parseOmiPeopleNames(JSON.stringify([{id: 'person-alex', name: null}])),
  ).toThrow();
  expect(() =>
    parseOmiPeopleNames(JSON.stringify([{id: 'person-alex'}])),
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
  const names = await loadOmiPeopleNames(backend);
  expect(names?.get('person-alex')).toBe('Alex Chen');
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/people?include_speech_samples=false',
  });
  request.mockResolvedValueOnce({id: 'people', status: 500, body: '[]'});
  expect(await loadOmiPeopleNames(backend)).toBeNull();
  request.mockResolvedValueOnce({id: 'people', status: 200, body: '{'});
  await expect(loadOmiPeopleNames(backend)).rejects.toThrow();
});

test('loadOmiPeopleNames keeps honest GET empty people', async () => {
  const request = jest.fn(async () => ({
    id: 'people',
    status: 200,
    body: JSON.stringify([]),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiPeopleNames(backend)).toEqual(new Map());
});

test('loadOmiPeopleNames omits HTTP 404 people instead of empty success', async () => {
  const request = jest.fn(async () => ({
    id: 'people',
    status: 404,
    body: null,
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiPeopleNames(backend)).toBeNull();
});

test('old people names name Flutter Person.fromGenerated padded GET created_at instead of omitting People', async () => {
  const request = jest.fn(async () => ({
    id: 'people',
    status: 200,
    body: JSON.stringify([
      {
        id: 'person-alex',
        name: 'Alex Chen',
        created_at: '  2026-09-07T00:00:00.000Z  ',
      },
    ]),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(loadOmiPeopleNames(backend)).rejects.toThrow(
    'Omi people are malformed',
  );
});
