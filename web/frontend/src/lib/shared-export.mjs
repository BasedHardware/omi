import {
  actionItemFacts,
  durationMinutes,
  eventFacts,
  formatDuration,
  meetingTypeLabel,
  participantFacts,
  shareDateTime,
  transcriptSpeakerResolver,
  transcriptTimestamp,
} from './shared-note.mjs';

// Explicit preferences only; */* remains the browser HTML default. Most-specific
// media ranges win within each representation, then quality and header order.
export function shareRepresentation(accept = '') {
  const ranges = accept
    .toLowerCase()
    .split(',')
    .map((entry, index) => {
      const [type, ...params] = entry.trim().split(';');
      const qParam = params.find((p) => p.trim().startsWith('q='));
      const q = qParam ? Number(qParam.trim().slice(2)) : 1;
      return {
        type: type.trim(),
        q: Number.isFinite(q) && q >= 0 && q <= 1 ? q : 0,
        index,
      };
    });
  const candidates = ['text/html', 'text/markdown', 'application/json']
    .map((type) => {
      const range =
        ranges.find((r) => r.type === type) ??
        (type === 'text/html'
          ? ranges.find((r) => r.type === 'text/*') ??
            ranges.find((r) => r.type === '*/*')
          : undefined);
      return { type, q: range?.q ?? 0, index: range?.index ?? Infinity };
    })
    .filter((r) => r.q > 0)
    .sort((a, b) => b.q - a.q || a.index - b.index);
  if (candidates.length > 0) return candidates[0].type;
  const htmlRejected = ranges.some(
    (range) =>
      range.q === 0 &&
      (range.type === 'text/html' || range.type === 'text/*' || range.type === '*/*'),
  );
  return htmlRejected ? null : 'text/html';
}

export function shareAlternates(id) {
  const path = `/conversations/${encodeURIComponent(id)}`;
  return { markdown: `${path}.md`, json: `${path}.json` };
}

export function shareLinkHeader(id) {
  const links = shareAlternates(id);
  return `<${links.markdown}>; rel="alternate"; type="text/markdown", <${links.json}>; rel="alternate"; type="application/json"`;
}

function inline(value) {
  return String(value ?? '')
    .replace(/\r?\n/g, ' ')
    .replace(/[\\`*_[\]<>#]/g, (ch) => `\\${ch}`);
}

export function sharedConversationMarkdown(memory, id) {
  const links = shareAlternates(id);
  const structured = memory.structured ?? {};
  const stamp = shareDateTime(memory);
  const duration = formatDuration(durationMinutes(memory.started_at, memory.finished_at));
  const lines = [
    `> Agents: fetch [Markdown](${links.markdown}) or [JSON](${links.json}); see [/llms.txt](/llms.txt).`,
    '',
    `# ${inline(structured.title || 'Conversation')}`,
    '',
    `When: ${stamp ? `${stamp.iso} (${stamp.label})` : 'Unknown'}`,
    `Duration: ${duration || 'Unknown'}`,
  ];
  if (structured.meeting_type)
    lines.push(`Meeting type: ${meetingTypeLabel(structured.meeting_type)}`);
  lines.push('', '## Participants', '');
  for (const participant of structured.participants ?? []) {
    const { name, details } = participantFacts(participant);
    lines.push(`- ${[name, ...details].map(inline).join(' — ')}`);
  }
  if (!structured.participants?.length) lines.push('Unknown');
  if (structured.overview) lines.push('', '## Overview', '', structured.overview);
  for (const section of structured.sections ?? []) {
    lines.push(
      '',
      `## ${inline(section.heading || 'Notes')}`,
      '',
      section.body_markdown || '',
    );
  }
  lines.push('', '## Action items', '');
  for (const item of structured.action_items ?? []) {
    const { owner, due, context } = actionItemFacts(item);
    lines.push(
      `- [${item.completed ? 'x' : ' '}] ${inline(item.description)}`,
      `  - Owner: ${inline(owner)}`,
      `  - Due: ${due ? `${due.iso} (${due.label})` : 'Unknown'}`,
    );
    if (context) lines.push(`  - Context: ${inline(context)}`);
  }
  if (!structured.action_items?.length) lines.push('None');
  if (structured.events?.length) {
    lines.push('', '## Events', '');
    for (const event of structured.events) {
      const facts = eventFacts(event);
      const when = facts.start ? `${facts.start.iso} (${facts.start.label})` : 'Unknown';
      const until = facts.end ? ` until ${facts.end.iso} (${facts.end.label})` : '';
      const duration = facts.duration ? `, ${facts.duration}` : '';
      lines.push(
        `- ${inline(facts.title || 'Untitled event')}: ${when}${until}${duration}`,
      );
      if (facts.description) lines.push(`  - ${inline(facts.description)}`);
    }
  }
  lines.push(
    '',
    '## Transcript',
    '',
    'Timestamps are offsets from the conversation start (HH:MM:SS).',
    '',
  );
  const resolveSpeaker = transcriptSpeakerResolver(
    memory.people,
    structured.participants,
    memory.transcript_segments,
  );
  for (const segment of memory.transcript_segments ?? []) {
    const name = resolveSpeaker(segment);
    lines.push(
      `**[${transcriptTimestamp(segment.start)}] ${inline(name)}:** ${inline(
        segment.text,
      )}`,
      '',
    );
  }
  if (!memory.transcript_segments?.length) lines.push('No available transcript.');
  return `${lines.join('\n')}\n`;
}
