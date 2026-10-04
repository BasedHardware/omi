import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  shareRepresentation,
  sharedConversationMarkdown,
  shareLinkHeader,
} from '../lib/shared-export.mjs';
import {
  transcriptSpeakerName,
  transcriptTimestamp,
  shareDateTime,
} from '../lib/shared-note.mjs';
const fixture = JSON.parse(
  readFileSync(new URL('../__fixtures__/agent-share.sample.json', import.meta.url)),
);

test('negotiates explicit machine preferences while preserving browser HTML', () => {
  for (const accept of [
    '',
    '*/*',
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'text/markdown;q=0',
    'application/json;q=0',
  ])
    assert.equal(shareRepresentation(accept), 'text/html');
  assert.equal(shareRepresentation('text/markdown'), 'text/markdown');
  assert.equal(shareRepresentation('application/json'), 'application/json');
  assert.equal(
    shareRepresentation('text/markdown;q=0.9,text/html;q=0.5'),
    'text/markdown',
  );
  assert.equal(
    shareRepresentation('application/json;q=0.8,text/markdown;q=0.5'),
    'application/json',
  );
  assert.equal(shareRepresentation('text/markdown;q=0.1,*/*'), 'text/html');
});

test('structured Markdown preserves public facts and marks unknown action facts', () => {
  const body = sharedConversationMarkdown(fixture, fixture.id);
  for (const fact of [
    '# Synthetic planning meeting',
    '2026-10-04T13:30:00.000Z',
    'UTC',
    '30 min',
    'Planning',
    'Example Labs',
    'Engineer',
    'Ship Thursday.',
    '[00:01:05] Ada Example',
    'Owner: Ada Example',
    '2026-10-05T16:00:00.000Z',
    'Context: For review',
    'Owner: Unknown',
    'Due: Unknown',
    '[x] Choose a venue',
  ])
    assert.ok(body.includes(fact), fact);
  assert.doesNotMatch(body, /Owner:\*\*|Speaker 0|<!DOCTYPE|@/i);
  assert.ok(body.startsWith('> Agents:'));
  assert.match(shareLinkHeader(fixture.id), /rel="alternate"; type="text\/markdown"/);
});

test('speaker identity uses explicit evidence, including owner person links, without roster-order guesses', () => {
  const people = fixture.people;
  const participants = fixture.structured.participants;
  assert.equal(
    transcriptSpeakerName(fixture.transcript_segments[0], people),
    'Ada Example',
  );
  assert.equal(
    transcriptSpeakerName(fixture.transcript_segments[1], [], participants),
    'Ada Example',
  );
  const unmapped = { speaker_id: 2, speaker: 'SPEAKER_02', is_user: false };
  assert.equal(transcriptSpeakerName(unmapped, people, participants), 'Speaker 2');
  assert.equal(
    transcriptSpeakerName(
      { ...unmapped, speaker_id: 0 },
      people,
      participants,
      fixture.transcript_segments,
    ),
    'Ada Example',
  );
  assert.equal(transcriptTimestamp(3665.5), '01:01:05');
  assert.equal(transcriptTimestamp(-1), 'Time unknown');
});

test('labels UTC independently of the runtime timezone', () => {
  const original = process.env.TZ;
  try {
    for (const tz of ['America/Los_Angeles', 'Asia/Tokyo']) {
      process.env.TZ = tz;
      const stamp = shareDateTime(fixture);
      assert.match(stamp.label, /1:30 PM UTC/);
      assert.equal(stamp.iso, '2026-10-04T13:30:00.000Z');
    }
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});
