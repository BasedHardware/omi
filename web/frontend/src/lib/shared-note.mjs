import { markdownToPlainText } from './markdown-to-plain-text.mjs';

const MEETING_TYPE_LABELS = {
  interview: 'Interview',
  intro: 'Intro call',
  sales: 'Sales call',
  customer: 'Customer call',
  one_on_one: 'One-on-one',
  team_sync: 'Team sync',
  planning: 'Planning',
  demo: 'Demo',
  social: 'Social',
  other: 'Other',
};

export function meetingTypeLabel(value) {
  if (typeof value !== 'string') return '';
  const key = value.trim().toLowerCase();
  if (!key) return '';
  if (MEETING_TYPE_LABELS[key]) return MEETING_TYPE_LABELS[key];
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

export function toValidDate(value) {
  if (value == null || value === '') return null;
  // Legacy backend timestamps without an offset are UTC, never viewer local time.
  const instant =
    typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(value)
      ? `${value}Z`
      : value;
  const date = instant instanceof Date ? instant : new Date(instant);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function shareDateTime(memory) {
  const date = toValidDate(memory?.started_at) ?? toValidDate(memory?.created_at);
  if (!date) return null;
  const sameYear = date.getUTCFullYear() === new Date().getUTCFullYear();
  const datePart = new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  }).format(date);
  const timePart = new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    timeZoneName: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
  return { iso: date.toISOString(), label: `${datePart} · ${timePart}` };
}

export function durationMinutes(start, end) {
  const a = toValidDate(start);
  const b = toValidDate(end);
  if (!a || !b) return null;
  const minutes = (b.getTime() - a.getTime()) / 60000;
  return minutes >= 0 ? Math.round(minutes) : null;
}

export function formatDuration(minutes) {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes) || minutes < 0) {
    return '';
  }
  const total = Math.round(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${total} min`;
  return rest === 0 ? `${hours} hr` : `${hours} hr ${rest} min`;
}

export function sortParticipants(participants) {
  if (!Array.isArray(participants)) return [];
  return participants
    .map((participant, index) => ({ participant, index }))
    .filter(({ participant }) => participant && typeof participant === 'object')
    .sort((a, b) => {
      const aiA = a.participant.is_ai_agent ? 1 : 0;
      const aiB = b.participant.is_ai_agent ? 1 : 0;
      return aiA - aiB || a.index - b.index;
    })
    .map(({ participant }) => participant);
}

export function participantDisplayName(participant) {
  const name = typeof participant?.name === 'string' ? participant.name.trim() : '';
  if (name) return name;
  const organization =
    typeof participant?.organization === 'string' ? participant.organization.trim() : '';
  return organization || 'Guest';
}

/** Name plus organization and role, without repeating the name as the organization. */
export function participantFacts(participant) {
  const name = participantDisplayName(participant);
  const organization =
    typeof participant?.organization === 'string' ? participant.organization.trim() : '';
  const role = typeof participant?.role === 'string' ? participant.role.trim() : '';
  return {
    name,
    details: [organization && organization !== name ? organization : '', role].filter(
      Boolean,
    ),
  };
}

export function participantInitials(displayName) {
  const words = String(displayName || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0][0].toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function avatarToneIndex(seed) {
  const text = String(seed || '');
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return ((hash % 6) + 6) % 6;
}

export function isSideNotes(section) {
  return section?.kind === 'side_notes';
}

export function sectionHasContent(section) {
  const heading = typeof section?.heading === 'string' ? section.heading.trim() : '';
  const body =
    typeof section?.body_markdown === 'string' ? section.body_markdown.trim() : '';
  return Boolean(heading || body);
}

export function splitSections(sections) {
  const mains = [];
  const sideNotes = [];
  if (!Array.isArray(sections)) return { mains, sideNotes };
  for (const section of sections) {
    if (!section || typeof section !== 'object' || !sectionHasContent(section)) {
      continue;
    }
    if (isSideNotes(section)) sideNotes.push(section);
    else mains.push(section);
  }
  return { mains, sideNotes };
}

function slugify(text) {
  return String(text || '')
    .toLowerCase()
    .trim()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function assignSectionIds(sections) {
  const counts = new Map();
  const list = Array.isArray(sections) ? sections : [];
  return list.map((section, index) => {
    const base = slugify(section?.heading) || `section-${index + 1}`;
    const seen = counts.get(base) || 0;
    counts.set(base, seen + 1);
    return seen === 0 ? base : `${base}-${seen + 1}`;
  });
}

const FENCE_RE = /^\s*(`{3,}|~{3,})/;
const BULLET_RE = /^\s{0,3}(?:[-*+]|\d{1,9}[.)])\s+(.+?)\s*$/;

export function firstBulletLine(markdown) {
  if (typeof markdown !== 'string' || !markdown.trim()) return '';
  let inFence = false;
  for (const rawLine of markdown.split('\n')) {
    if (FENCE_RE.test(rawLine)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = BULLET_RE.exec(rawLine);
    if (match) return match[1];
  }
  return '';
}

export function firstSectionBulletPlainText(sections) {
  if (!Array.isArray(sections)) return '';
  for (const section of sections) {
    if (!section || typeof section !== 'object' || isSideNotes(section)) continue;
    if (typeof section.body_markdown !== 'string' || !section.body_markdown.trim()) {
      continue;
    }
    return markdownToPlainText(firstBulletLine(section.body_markdown));
  }
  return '';
}

function bulletLines(markdown) {
  if (typeof markdown !== 'string' || !markdown.trim()) return [];
  const lines = [];
  let inFence = false;
  for (const rawLine of markdown.split('\n')) {
    if (FENCE_RE.test(rawLine)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = BULLET_RE.exec(rawLine);
    // Top-level bullets only: nested ones repeat their parent's point.
    if (match && !/^\s{2,}/.test(rawLine)) lines.push(match[1]);
  }
  return lines;
}

/**
 * Up to `max` short plain-text points for the link-preview image: the first
 * main section's bullets, else the overview's. Older notes have no sections
 * and keep everything in the overview markdown.
 */
export function previewBullets(structured, max = 3, maxLength = 64) {
  const { mains } = splitSections(structured?.sections);
  const sources = [...mains.map((s) => s.body_markdown), structured?.overview];
  for (const markdown of sources) {
    const points = bulletLines(markdown)
      .map((line) => markdownToPlainText(line, maxLength))
      .filter(Boolean);
    if (points.length > 0) return points.slice(0, max);
  }
  return [];
}

/** Transcript offsets are elapsed seconds from the conversation start. */
export function transcriptTimestamp(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0)
    return 'Time unknown';
  const total = Math.floor(seconds);
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map((part) => String(part).padStart(2, '0'))
    .join(':');
}

const EMAIL_RE = /[^\s@]+@[^\s@]+\.[^\s@]+/;

/**
 * Resolve every turn once. Person links and an exact participant-name match are
 * the only identities. Roster order is never a guess, and an unmatched speaker
 * string is not a name.
 */
export function transcriptSpeakerResolver(
  people = [],
  participants = [],
  transcript = [],
) {
  const peopleById = new Map();
  for (const person of people ?? []) {
    const name = person?.name?.trim();
    if (person?.id && name) peopleById.set(person.id, name);
  }
  const namesBySpeaker = new Map();
  for (const turn of transcript ?? []) {
    if (turn?.speaker_id == null || !turn.person_id) continue;
    const name = peopleById.get(turn.person_id);
    if (!name) continue;
    const current = namesBySpeaker.get(turn.speaker_id);
    if (current === undefined) namesBySpeaker.set(turn.speaker_id, name);
    else if (current !== name) namesBySpeaker.set(turn.speaker_id, '');
  }
  const participantsByName = new Map();
  for (const participant of participants ?? []) {
    const name = participant?.name?.trim();
    if (!name) continue;
    const key = name.toLowerCase();
    if (!participantsByName.has(key)) participantsByName.set(key, name);
  }
  return function resolveSpeaker(segment) {
    const direct = segment?.person_id ? peopleById.get(segment.person_id) : '';
    if (direct) return direct;
    if (segment?.speaker_id != null && namesBySpeaker.has(segment.speaker_id)) {
      const shared = namesBySpeaker.get(segment.speaker_id);
      if (shared) return shared;
    }
    const speaker = segment?.speaker?.trim();
    const participant = speaker ? participantsByName.get(speaker.toLowerCase()) : '';
    if (participant) return participant;
    if (segment?.is_user) return 'Owner';
    if (segment?.speaker_id != null) return `Speaker ${segment.speaker_id}`;
    return 'Speaker unknown';
  };
}

/** Never assign roster names by array order: the roster has no speaker IDs. */
export function transcriptSpeakerName(
  segment,
  people = [],
  participants = [],
  transcript = [],
) {
  return transcriptSpeakerResolver(people, participants, transcript)(segment);
}

export function actionItemFacts(item) {
  const due = shareDateTime({ started_at: item?.due_at });
  const rawOwner = typeof item?.owner_name === 'string' ? item.owner_name.trim() : '';
  return {
    owner: rawOwner && !EMAIL_RE.test(rawOwner) ? rawOwner : 'Unknown',
    due,
    context: item?.context?.trim() || '',
  };
}

export function eventFacts(event) {
  const start = shareDateTime({ started_at: event?.start });
  const startDate = toValidDate(event?.start);
  const minutes =
    typeof event?.duration === 'number' &&
    Number.isFinite(event.duration) &&
    event.duration >= 0
      ? Math.round(event.duration)
      : null;
  const end =
    startDate && minutes != null
      ? shareDateTime({ started_at: new Date(startDate.getTime() + minutes * 60000) })
      : null;
  return {
    title: typeof event?.title === 'string' ? event.title.trim() : '',
    description: typeof event?.description === 'string' ? event.description.trim() : '',
    start,
    end,
    duration: minutes == null ? '' : formatDuration(minutes),
  };
}
