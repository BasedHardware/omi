export interface NoteSectionInput {
  heading?: string | null;
  body_markdown?: string | null;
  kind?: string | null;
}

export function isFirstPartyNoteSelection(kind: string, sections: unknown): boolean {
  return kind === 'sections' && Array.isArray(sections) && sections.length > 0;
}

function hasContent(section: NoteSectionInput): boolean {
  const heading = (section.heading ?? '').trim();
  const body = (section.body_markdown ?? '').trim();
  return Boolean(heading || body);
}

export function splitNoteSections<T extends NoteSectionInput>(
  sections: T[] | null | undefined,
): { mains: T[]; sideNotes: T[] } {
  const mains: T[] = [];
  const sideNotes: T[] = [];
  if (!Array.isArray(sections)) return { mains, sideNotes };
  for (const section of sections) {
    if (!section || !hasContent(section)) continue;
    if (section.kind === 'side_notes') sideNotes.push(section);
    else mains.push(section);
  }
  return { mains, sideNotes };
}

const MEETING_TYPE_LABELS: Record<string, string> = {
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

export function meetingTypeLabel(value: unknown): string {
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

export interface NoteParticipantLike {
  name?: string | null;
  email?: string | null;
  organization?: string | null;
  role?: string | null;
  is_ai_agent?: boolean | null;
  source?: 'roster' | 'transcript' | null;
}

export function sortNoteParticipants<T extends NoteParticipantLike>(
  participants: T[] | null | undefined,
): T[] {
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

export function noteParticipantName(participant: NoteParticipantLike): string {
  const name = typeof participant?.name === 'string' ? participant.name.trim() : '';
  if (name) return name;
  const organization =
    typeof participant?.organization === 'string' ? participant.organization.trim() : '';
  return organization || 'Guest';
}

export function noteParticipantInitials(displayName: string): string {
  const words = String(displayName || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0][0].toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function noteAvatarToneIndex(seed: string): number {
  const text = String(seed || '');
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return ((hash % 6) + 6) % 6;
}
