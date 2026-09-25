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
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function shareDateTime(memory) {
  const date = toValidDate(memory?.started_at) ?? toValidDate(memory?.created_at);
  if (!date) return null;
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const datePart = new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  }).format(date);
  const timePart = new Intl.DateTimeFormat('en-US', {
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
  const name =
    typeof participant?.name === 'string' ? participant.name.trim() : '';
  if (name) return name;
  const organization =
    typeof participant?.organization === 'string'
      ? participant.organization.trim()
      : '';
  return organization || 'Guest';
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
  const heading =
    typeof section?.heading === 'string' ? section.heading.trim() : '';
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
    if (
      typeof section.body_markdown !== 'string' ||
      !section.body_markdown.trim()
    ) {
      continue;
    }
    return markdownToPlainText(firstBulletLine(section.body_markdown));
  }
  return '';
}
