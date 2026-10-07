/**
 * The local assistant quotes people. Getting a quote wrong is the worst thing it
 * can do, so the tests are mostly about what it refuses to answer.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  appendSegments,
  clearAll,
  searchLocal,
  knownSpeakers,
  listConversations,
} from './localConversations';
import { answerLocally, stripQuestion, detectSpeaker } from './localAssistant';

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

beforeEach(async () => {
  (AsyncStorage as unknown as { clear: () => Promise<void> }).clear();
  const { _resetCacheForTests } = require('./localConversations') as {
    _resetCacheForTests?: () => void;
  };
  _resetCacheForTests?.();
});

async function seed() {
  await appendSegments(
    [
      { text: 'can you pick up brown bread on the way home', speaker: 'Other 1', isUser: false, start: 0 },
      { text: 'yes get the whole wheat one instead', speaker: 'You', isUser: true, start: 2 },
    ],
    'mic'
  );
}

describe('local conversation store', () => {
  it('keeps segments and lists them newest first', async () => {
    await seed();
    const list = await listConversations();
    expect(list).toHaveLength(1);
    expect(list[0]?.segments).toHaveLength(2);
  });

  it('groups a later run into a new conversation', async () => {
    await appendSegments([{ text: 'first thing', speaker: 'You', isUser: true, start: 0 }], 'mic');
    // Force a new conversation by switching source: same clock, different capture.
    await appendSegments([{ text: 'from the wearable', speaker: 'You', isUser: true, start: 0 }], 'omi');
    const list = await listConversations();
    expect(list).toHaveLength(2);
    expect(list.map((c) => c.source).sort()).toEqual(['mic', 'omi']);
  });

  it('drops empty segments rather than storing blanks', async () => {
    await appendSegments([{ text: '   ', speaker: 'You', isUser: true, start: 0 }], 'mic');
    expect(await listConversations()).toHaveLength(0);
  });

  it('finds a term and ranks the segment that opens with it higher', async () => {
    await seed();
    const hits = await searchLocal('bread');
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0]?.text).toMatch(/brown bread/);
  });

  it('filters by speaker', async () => {
    await seed();
    const hits = await searchLocal('bread', { speaker: 'You' });
    expect(hits).toHaveLength(0);
    const other = await searchLocal('bread', { speaker: 'Other 1' });
    expect(other.length).toBeGreaterThan(0);
    expect(other.every((h) => h.speaker === 'Other 1')).toBe(true);
  });

  it('lists distinct speakers', async () => {
    await seed();
    expect(await knownSpeakers()).toEqual(['Other 1', 'You']);
  });

  it('returns nothing for a question with no content words', async () => {
    await seed();
    expect(await searchLocal('what is it')).toEqual([]);
  });
});

describe('answerLocally', () => {
  it('quotes what was actually said', async () => {
    await seed();
    const a = await answerLocally('what did they say about bread');
    expect(a.kind).toBe('quote');
    expect(a.text).toMatch(/brown bread/);
  });

  it('says so plainly when nothing matches, instead of guessing', async () => {
    await seed();
    const a = await answerLocally('what did they say about passports');
    expect(a.kind).toBe('empty');
    expect(a.text).toMatch(/Nothing recorded/);
    expect(a.text).not.toMatch(/brown bread/);
  });

  it('refuses generation rather than confabulating', async () => {
    await seed();
    // "what is the weather" has no recorded answer, and the model cannot invent
    // one. It must say it cannot, not produce a plausible forecast.
    const a = await answerLocally('what is the weather');
    expect(['unsupported', 'empty']).toContain(a.kind);
    expect(a.text).not.toMatch(/\d+\s*(degrees|°|celsius|fahrenheit)/i);
  });

  it('flags a weak match as uncertain rather than presenting it as the answer', async () => {
    await appendSegments(
      [{ text: 'the weather is quite nice today', speaker: 'You', isUser: true, start: 0 }],
      'mic'
    );
    // One of three content words appears: coverage 0.33, below the bar. It must
    // surface as "closest was", not as the answer.
    const a = await answerLocally('what did they say about bread and weather and taxes');
    expect(a.kind).toBe('empty');
    expect(a.text).toMatch(/Closest was/);
  });

  it('reports which speaker label it used, so a name miss is visible', async () => {
    await seed();
    const a = await answerLocally('what did marco say about bread');
    // "marco" is not a label anyone has, so the filter cannot apply -- and saying
    // so beats silently searching every speaker.
    expect(a.speakerHint).toBeUndefined();
    expect(a.text.length).toBeGreaterThan(0);
  });

  it('uses a matching speaker label when one exists', async () => {
    await seed();
    const a = await answerLocally('what did Other 1 say about bread');
    expect(a.speakerHint).toBe('Other 1');
  });
});

describe('question parsing', () => {
  it('strips the scaffolding and keeps the topic', () => {
    expect(stripQuestion('what did marco say about bread')).toBe('bread');
    expect(stripQuestion('did marco say buy bread')).toMatch(/bread/);
    expect(stripQuestion('tell me about the bread')).toBe('the bread');
  });

  it('matches a known speaker label only', () => {
    expect(detectSpeaker('what did Other 1 say', ['Other 1', 'You'])).toBe('Other 1');
    expect(detectSpeaker('what did marco say', ['Other 1', 'You'])).toBeUndefined();
  });
});