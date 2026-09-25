import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  assignSectionIds,
  avatarToneIndex,
  durationMinutes,
  firstSectionBulletPlainText,
  formatDuration,
  meetingTypeLabel,
  participantDisplayName,
  participantInitials,
  shareDateTime,
  sortParticipants,
  splitSections,
} from '../lib/shared-note.mjs';

const fixture = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/shared-note.sample.json', import.meta.url),
    'utf8',
  ),
);

const pageSource = readFileSync(
  new URL('../app/memories/[id]/page.tsx', import.meta.url),
  'utf8',
);
const summarySource = readFileSync(
  new URL('../components/memories/summary/sumary.tsx', import.meta.url),
  'utf8',
);
const cssSource = readFileSync(
  new URL('../app/memories/[id]/share-note.css', import.meta.url),
  'utf8',
);

const SHARE_RENDER_SOURCES = [
  '../app/memories/[id]/page.tsx',
  '../app/memories/[id]/not-found.tsx',
  '../components/memories/memory.tsx',
  '../components/memories/memory-header.tsx',
  '../components/memories/summary/sumary.tsx',
  '../components/memories/summary/action-items.tsx',
  '../components/memories/summary/memory-with-tabs.tsx',
  '../components/memories/events/memory-events.tsx',
  '../components/memories/tabs.tsx',
  '../components/memories/shared-conversation-install-cta.tsx',
  '../components/memories/transcript/transcription.tsx',
  '../components/memories/transcript/transcription-segment.tsx',
  '../components/memories/external-data/external-data.tsx',
  '../components/memories/plugins/plugins.tsx',
  '../components/plugins/identify-plugin.tsx',
].map((path) => [path, readFileSync(new URL(path, import.meta.url), 'utf8')]);

describe('firstSectionBulletPlainText', () => {
  it('returns empty for missing or empty sections (old-payload fallback)', () => {
    assert.equal(firstSectionBulletPlainText(undefined), '');
    assert.equal(firstSectionBulletPlainText(null), '');
    assert.equal(firstSectionBulletPlainText([]), '');
    assert.equal(firstSectionBulletPlainText('nope'), '');
  });

  it('returns empty when the first main section has no bullet', () => {
    const sections = [
      { kind: 'main', heading: 'Notes', body_markdown: 'Just a paragraph.' },
    ];
    assert.equal(firstSectionBulletPlainText(sections), '');
  });

  it('extracts the first bullet of the first main section as plain text', () => {
    const sections = [
      {
        kind: 'main',
        heading: 'Takeaways',
        body_markdown:
          'Intro line.\n- **Launch date** confirmed for March 18.\n- Second bullet',
      },
    ];
    assert.equal(
      firstSectionBulletPlainText(sections),
      'Launch date confirmed for March 18.',
    );
  });

  it('skips side_notes sections when looking for the first bullet', () => {
    const sections = [
      {
        kind: 'side_notes',
        heading: 'Aside',
        body_markdown: '- hidden aside bullet',
      },
      { kind: 'main', heading: 'Main', body_markdown: '- visible bullet' },
    ];
    assert.equal(firstSectionBulletPlainText(sections), 'visible bullet');
  });

  it('does not fall through to later main sections', () => {
    const sections = [
      { kind: 'main', heading: 'First', body_markdown: 'No bullets here.' },
      { kind: 'main', heading: 'Second', body_markdown: '- later bullet' },
    ];
    assert.equal(firstSectionBulletPlainText(sections), '');
  });
});

describe('splitSections', () => {
  it('returns empty groups for missing input', () => {
    assert.deepEqual(splitSections(undefined), { mains: [], sideNotes: [] });
    assert.deepEqual(splitSections(null), { mains: [], sideNotes: [] });
  });

  it('keeps content-bearing mains in order and collects the side note', () => {
    const { mains, sideNotes } = splitSections(fixture.structured.sections);
    assert.equal(mains.length, 4);
    assert.equal(sideNotes.length, 1);
    assert.equal(sideNotes[0].heading, 'Side notes');
    assert.deepEqual(
      mains.map((s) => s.heading),
      ['Key takeaways', 'Decisions', 'Discussion notes', 'Risks'],
    );
  });

  it('drops fully blank sections', () => {
    const { mains, sideNotes } = splitSections([
      { kind: 'main', heading: '  ', body_markdown: '' },
      { kind: 'main', heading: 'Real', body_markdown: '- item' },
      { kind: 'side_notes', heading: '', body_markdown: '  ' },
    ]);
    assert.equal(mains.length, 1);
    assert.equal(sideNotes.length, 0);
  });
});

describe('assignSectionIds', () => {
  it('produces stable unique ids for duplicate headings', () => {
    const ids = assignSectionIds([
      { heading: 'Next steps' },
      { heading: 'Next steps' },
      { heading: 'next steps' },
      { heading: '' },
    ]);
    assert.deepEqual(ids, [
      'next-steps',
      'next-steps-2',
      'next-steps-3',
      'section-4',
    ]);
    assert.equal(new Set(ids).size, ids.length);
  });
});

describe('participants', () => {
  it('sorts humans first and AI agents last, stable within groups', () => {
    const sorted = sortParticipants([
      { name: 'Zed Agent', is_ai_agent: true },
      { name: 'Anna' },
      { name: 'Boardy', is_ai_agent: true },
      { name: 'Ben' },
    ]);
    assert.deepEqual(
      sorted.map((p) => p.name),
      ['Anna', 'Ben', 'Zed Agent', 'Boardy'],
    );
  });

  it('puts the fixture AI participant last', () => {
    const sorted = sortParticipants(fixture.structured.participants);
    assert.equal(sorted.at(-1).name, 'Boardy');
    assert.equal(sorted.at(-1).is_ai_agent, true);
  });

  it('falls back name -> organization -> Guest', () => {
    assert.equal(participantDisplayName({ name: 'Priya Raman' }), 'Priya Raman');
    assert.equal(
      participantDisplayName({ name: '  ', organization: 'Northwind Labs' }),
      'Northwind Labs',
    );
    assert.equal(participantDisplayName({}), 'Guest');
    assert.equal(participantDisplayName(null), 'Guest');
  });

  it('derives compact initials and a deterministic avatar tone', () => {
    assert.equal(participantInitials('Priya Raman'), 'PR');
    assert.equal(participantInitials('Boardy'), 'B');
    assert.equal(participantInitials(''), '?');
    const tone = avatarToneIndex('Priya Raman');
    assert.equal(tone, avatarToneIndex('Priya Raman'));
    assert.ok(tone >= 0 && tone <= 5);
  });
});

describe('shareDateTime and duration', () => {
  it('prefers started_at and falls back to created_at', () => {
    const stamp = shareDateTime({
      started_at: '2025-03-04T14:30:00.000Z',
      created_at: '2025-03-04T15:20:00.000Z',
    });
    assert.equal(stamp.iso, '2025-03-04T14:30:00.000Z');

    const fallback = shareDateTime({
      started_at: 'not-a-date',
      created_at: '2025-03-04T15:20:00.000Z',
    });
    assert.equal(fallback.iso, '2025-03-04T15:20:00.000Z');

    const absent = shareDateTime({ created_at: '2025-03-04T15:20:00.000Z' });
    assert.equal(absent.iso, '2025-03-04T15:20:00.000Z');
  });

  it('returns null when no usable timestamp exists', () => {
    assert.equal(shareDateTime({}), null);
    assert.equal(shareDateTime({ started_at: null, created_at: 'bad' }), null);
  });

  it('only yields a duration for valid nonnegative start/end', () => {
    assert.equal(
      durationMinutes('2025-03-04T14:30:00Z', '2025-03-04T15:17:00Z'),
      47,
    );
    assert.equal(durationMinutes('bad', '2025-03-04T15:17:00Z'), null);
    assert.equal(durationMinutes('2025-03-04T14:30:00Z', null), null);
    assert.equal(
      durationMinutes('2025-03-04T16:00:00Z', '2025-03-04T15:00:00Z'),
      null,
    );
    assert.equal(formatDuration(47), '47 min');
    assert.equal(formatDuration(60), '1 hr');
    assert.equal(formatDuration(75), '1 hr 15 min');
  });
});

describe('meetingTypeLabel', () => {
  it('maps known types to friendly labels', () => {
    assert.equal(meetingTypeLabel('interview'), 'Interview');
    assert.equal(meetingTypeLabel('intro'), 'Intro call');
    assert.equal(meetingTypeLabel('sales'), 'Sales call');
    assert.equal(meetingTypeLabel('customer'), 'Customer call');
    assert.equal(meetingTypeLabel('one_on_one'), 'One-on-one');
    assert.equal(meetingTypeLabel('team_sync'), 'Team sync');
    assert.equal(meetingTypeLabel('planning'), 'Planning');
    assert.equal(meetingTypeLabel('demo'), 'Demo');
    assert.equal(meetingTypeLabel('social'), 'Social');
    assert.equal(meetingTypeLabel('other'), 'Other');
  });

  it('humanizes unknown types and rejects empty input', () => {
    assert.equal(meetingTypeLabel('deep_dive'), 'Deep Dive');
    assert.equal(meetingTypeLabel(''), '');
    assert.equal(meetingTypeLabel(null), '');
    assert.equal(meetingTypeLabel(undefined), '');
  });
});

describe('share note page wiring', () => {
  it('scopes the route through share-note.css with light/dark schemes', () => {
    assert.match(pageSource, /share-note\.css/);
    assert.match(pageSource, /className="share-note"/);
    assert.match(cssSource, /\.share-note/);
    assert.match(cssSource, /prefers-color-scheme:\s*dark/);
  });

  it('derives metadata from the first section bullet before the overview fallback', () => {
    assert.match(pageSource, /firstSectionBulletPlainText/);
    assert.match(pageSource, /markdownToPlainText\(memory\?\.structured\?\.overview\)/);
  });

  it('renders structured sections on the Summary tab with the overview fallback intact', () => {
    assert.match(summarySource, /structured\?\.sections/);
    assert.match(summarySource, /structured\?\.overview/);
    assert.match(summarySource, /\{overview\}/);
    assert.match(summarySource, /In this note/);
  });

  it('clears the fixed global header and keeps markdown bullets visible', () => {
    const pagePadding = cssSource.match(
      /\.share-note \.sn-page \{[^}]*padding:\s*(\d+)px/,
    );
    assert.ok(pagePadding, '.sn-page must define padding');
    assert.ok(
      Number(pagePadding[1]) >= 88,
      '.sn-page top padding must clear the fixed global header',
    );
    assert.match(cssSource, /\.sn-md ul\s*,[^}]*list-style-type:\s*disc/);
    assert.match(cssSource, /\.sn-md ol\s*,[^}]*list-style-type:\s*decimal/);
    assert.match(
      cssSource,
      /\.sn-md (?:ul|ol) ul\s*,[^}]*list-style-type:\s*circle/,
    );
    assert.match(cssSource, /li::marker\s*\{[^}]*--sn-muted/);
  });

  it('styles the root list element when markdown-to-jsx renders sn-md on it', () => {
    const rootListRules = [
      [/\bul\.sn-md\s*[,{][^}]*list-style-type:\s*disc/, 'ul.sn-md disc'],
      [/\bol\.sn-md\s*[,{][^}]*list-style-type:\s*decimal/, 'ol.sn-md decimal'],
      [/\bul\.sn-md\s*[,{][^}]*padding-left/, 'ul.sn-md indentation'],
      [/\bol\.sn-md\s*[,{][^}]*padding-left/, 'ol.sn-md indentation'],
      [/\bul\.sn-md ul\s*[,{][^}]*list-style-type:\s*circle/, 'ul.sn-md ul circle'],
      [/\bol\.sn-md ul\s*[,{][^}]*list-style-type:\s*circle/, 'ol.sn-md ul circle'],
      [/\bul\.sn-md ul ul\s*[,{][^}]*list-style-type:\s*square/, 'ul.sn-md ul ul square'],
      [/\bol\.sn-md ul ul\s*[,{][^}]*list-style-type:\s*square/, 'ol.sn-md ul ul square'],
    ];
    for (const [pattern, label] of rootListRules) {
      assert.match(
        cssSource,
        pattern,
        `share-note.css must style the root list element: ${label}`,
      );
    }
  });

  it('passes className="sn-md" to every section markdown renderer', () => {
    const markdownTags = summarySource.match(/<Markdown[^>]*>/g) ?? [];
    assert.ok(
      markdownTags.length >= 3,
      'expected the summary tab to render markdown sections',
    );
    for (const tag of markdownTags) {
      assert.match(
        tag,
        /className="sn-md"/,
        `markdown renderer missing sn-md scope: ${tag}`,
      );
    }
  });

  it('uses h2 for all structural share headings', () => {
    const structuralSources = SHARE_RENDER_SOURCES.filter(([path]) =>
      /sumary|action-items|memory-events|transcription\.tsx|external-data/.test(
        path,
      ),
    );
    for (const [path, source] of structuralSources) {
      assert.doesNotMatch(
        source,
        /<h3[\s>]/,
        `${path} must not use h3 for top-level share headings`,
      );
    }
    assert.match(summarySource, /<h2 className="sn-h3">/);
  });
});

describe('shared note privacy contract', () => {
  it('never reads or renders owner-only fields in any share surface', () => {
    for (const [path, source] of SHARE_RENDER_SOURCES) {
      assert.doesNotMatch(source, /insights/i, `${path} must not touch insights`);
    }
  });

  it('never renders participant emails in share components', () => {
    for (const [path, source] of SHARE_RENDER_SOURCES) {
      assert.doesNotMatch(
        source,
        /\.email\b/,
        `${path} must not render participant email`,
      );
    }
  });
});

describe('shared-note fixture contract', () => {
  const structured = fixture.structured;

  it('matches the backend share-note payload shape', () => {
    const meetingTypes = new Set([
      'interview',
      'intro',
      'sales',
      'customer',
      'one_on_one',
      'team_sync',
      'planning',
      'demo',
      'social',
      'other',
    ]);
    assert.ok(
      meetingTypes.has(structured.meeting_type),
      `unexpected meeting_type ${structured.meeting_type}`,
    );

    const sections = structured.sections;
    assert.ok(Array.isArray(sections) && sections.length >= 5);
    for (const section of sections) {
      assert.ok(
        section.kind === 'main' || section.kind === 'side_notes',
        `unexpected section kind ${section.kind}`,
      );
      assert.ok(Array.isArray(section.source_segment_ids));
    }
    const sideNotes = sections.filter((s) => s.kind === 'side_notes');
    assert.equal(sideNotes.length, 1);
    assert.equal(sideNotes[0].heading, 'Side notes');
    assert.equal(
      sideNotes[0],
      sections.at(-1),
      'side_notes must be the last section',
    );
    assert.ok(sections.filter((s) => s.kind === 'main').length >= 4);

    const participantSources = new Set(['roster', 'transcript']);
    for (const participant of structured.participants) {
      assert.ok(participantSources.has(participant.source));
      assert.equal(typeof participant.is_ai_agent, 'boolean');
    }
    assert.ok(
      structured.participants.some((p) => p.is_ai_agent),
      'fixture needs an AI participant',
    );

    assert.ok(structured.action_items.length > 0);
    assert.ok(structured.events.length > 0);
  });

  it('contains no owner-only insights and no real email addresses', () => {
    assert.ok(
      !('insights' in structured),
      'public share fixture must not carry insights',
    );
    for (const participant of structured.participants) {
      assert.equal(participant.email ?? null, null);
    }
    assert.doesNotMatch(
      JSON.stringify(fixture),
      /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/,
      'fixture must not contain email addresses',
    );
  });
});
