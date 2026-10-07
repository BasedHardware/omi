import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * Conversations on the device.
 *
 * The server is the source of truth when there is a session, but there often is
 * not one: a guest session has no token, every /v1 call 401s, and search returns
 * nothing because nothing has ever synced. This store is what makes the local
 * surface useful without an account -- captured audio lands here, and the
 * assistant reads from here.
 *
 * Deliberately lexical, not semantic. Matching is term-based so it is honest
 * about what it can answer. Semantic search over these segments is possible --
 * the MiniLM model is already loaded for routing and can embed text -- but it is
 * a separate piece of work and pretending token overlap is meaning would be
 * worse than saying so.
 */

export type CaptureSource = 'mic' | 'omi';

export interface StoredSegment {
  id: string;
  text: string;
  /** Label the voiceprint assigned: "You", "Other 1", ... */
  speaker: string;
  isUser: boolean;
  /** Epoch ms. */
  startedAt: number;
  source: CaptureSource;
}

export interface StoredConversation {
  id: string;
  title: string;
  /** Epoch ms. */
  startedAt: number;
  endedAt: number | null;
  source: CaptureSource;
  segments: StoredSegment[];
}

export interface SearchHit {
  conversationId: string;
  segmentId: string;
  text: string;
  speaker: string;
  isUser: boolean;
  startedAt: number;
  score: number;
}

const KEY = 'local.conversations.v1';
/** A run of segments with a gap this large starts a new conversation. */
const CONVERSATION_GAP_MS = 5 * 60 * 1000;
/** Conversations kept on device. Old audio is cheap to drop and not free to keep. */
const MAX_CONVERSATIONS = 200;

let cache: StoredConversation[] | null = null;

function nowMs(): number {
  return Date.now();
}

function newId(): string {
  return `lc_${nowMs().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

async function load(): Promise<StoredConversation[]> {
  if (cache) return cache;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    const parsed = raw ? (JSON.parse(raw) as StoredConversation[]) : [];
    cache = Array.isArray(parsed) ? parsed : [];
  } catch {
    // Corrupt or unreadable storage must not take the app down; start empty rather
    // than throwing out of a capture path.
    cache = [];
  }
  return cache;
}

async function persist(list: StoredConversation[]): Promise<void> {
  cache = list;
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(list));
  } catch (e) {
    console.warn('[localConversations] persist failed:', e);
  }
}

/**
 * Appends captured segments, grouping them into conversations.
 *
 * Continues the last conversation when it is the same source and recent enough;
 * otherwise starts a new one. Time-based because a capture session is what a
 * person means by "a conversation", not a fixed clock bucket.
 */
export async function appendSegments(
  segments: ReadonlyArray<{ text: string; speaker: string; isUser?: boolean; start: number }>,
  source: CaptureSource
): Promise<StoredConversation | null> {
  const final = segments.filter((s) => s.text.trim().length > 0);
  if (final.length === 0) return null;

  const list = await load();
  const startedAt = nowMs();
  const last = list[list.length - 1];

  const continues =
    !!last &&
    last.source === source &&
    startedAt - (last.endedAt ?? last.startedAt) < CONVERSATION_GAP_MS;

  if (continues && last) {
    const added: StoredSegment[] = final.map((s) => ({
      id: newId(),
      text: s.text.trim(),
      speaker: s.speaker,
      // Optional on the way in: TranscriptSegment carries speaker/isUser, but a
      // segment arriving from elsewhere may not, and defaulting to "not the user"
      // is safer than dropping the sentence.
      isUser: s.isUser ?? false,
      startedAt,
      source,
    }));
    last.segments.push(...added);
    last.endedAt = startedAt;
    await persist(list);
    return last;
  }

  const convo: StoredConversation = {
    id: newId(),
    title: '',
    startedAt,
    endedAt: startedAt,
    source,
    segments: final.map((s) => ({
      id: newId(),
      text: s.text.trim(),
      speaker: s.speaker,
      isUser: s.isUser ?? false,
      startedAt,
      source,
    })),
  };
  convo.title = deriveTitle(convo);

  const next = [...list, convo].slice(-MAX_CONVERSATIONS);
  await persist(next);
  return convo;
}

/** First meaningful words, so a list is scannable before anything is read. */
export function deriveTitle(convo: StoredConversation): string {
  const first = convo.segments.find((s) => !s.isUser) ?? convo.segments[0];
  if (!first) return 'Empty conversation';
  const trimmed = first.text.trim();
  return trimmed.length > 48 ? `${trimmed.slice(0, 45)}…` : trimmed;
}

export async function listConversations(): Promise<StoredConversation[]> {
  const list = await load();
  return [...list].reverse();
}

export async function getConversation(id: string): Promise<StoredConversation | null> {
  const list = await load();
  return list.find((c) => c.id === id) ?? null;
}

export async function clearAll(): Promise<void> {
  await persist([]);
}

const STOP = new Set([
  'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be',
  'to', 'of', 'in', 'on', 'at', 'for', 'with', 'it', 'that', 'this', 'did',
  'do', 'does', 'i', 'you', 'he', 'she', 'we', 'they', 'my', 'your', 'me',
]);

export function terms(query: string): string[] {
  return query
    .toLowerCase()
    .replace(/[^a-z0-9\s']/g, ' ')
    .split(/\s+/)
    .filter((t) => t.length > 1 && !STOP.has(t));
}

/**
 * Ranks stored segments against a query, optionally restricted to one speaker.
 *
 * The score is term coverage with a bonus for earlier matches in a segment, which
 * is enough to answer "did marco say buy brown bread or white bread" against a
 * few hundred segments -- and it is honest about being lexical.
 *
 * @param speaker Speaker label to restrict to. Matched loosely, so "marco" finds
 *   a segment labelled "Other 2" only if that label contains it; see the note in
 *   localAssistant about why speaker_id needs a real session.
 */
export async function searchLocal(
  query: string,
  opts: { speaker?: string; limit?: number; sinceDays?: number } = {}
): Promise<SearchHit[]> {
  const { speaker, limit = 8, sinceDays } = opts;
  const wanted = terms(query);
  if (wanted.length === 0) return [];

  const list = await load();
  const cutoff = sinceDays ? nowMs() - sinceDays * 86400_000 : 0;
  const speakerNeedle = speaker?.trim().toLowerCase();
  const hits: SearchHit[] = [];

  for (const convo of list) {
    for (const seg of convo.segments) {
      if (cutoff && seg.startedAt < cutoff) continue;
      if (speakerNeedle && !seg.speaker.toLowerCase().includes(speakerNeedle)) continue;

      const hay = seg.text.toLowerCase();
      let matched = 0;
      let firstIndex = -1;
      for (const t of wanted) {
        const i = hay.indexOf(t);
        if (i >= 0) {
          matched += 1;
          if (firstIndex < 0 || i < firstIndex) firstIndex = i;
        }
      }
      if (matched === 0) continue;

      // Coverage dominates; the positional term breaks ties toward the segment
      // that opens with the topic, which is usually the informative one.
      const coverage = matched / wanted.length;
      const positionBonus = firstIndex >= 0 ? 0.15 * (1 - Math.min(firstIndex / 400, 1)) : 0;
      hits.push({
        conversationId: convo.id,
        segmentId: seg.id,
        text: seg.text,
        speaker: seg.speaker,
        isUser: seg.isUser,
        startedAt: seg.startedAt,
        score: Number((coverage + positionBonus).toFixed(4)),
      });
    }
  }

  return hits.sort((a, b) => b.score - a.score || b.startedAt - a.startedAt).slice(0, limit);
}

/** Distinct speaker labels across stored conversations. */
export async function knownSpeakers(): Promise<string[]> {
  const list = await load();
  const set = new Set<string>();
  for (const c of list) for (const s of c.segments) set.add(s.speaker);
  return [...set].sort();
}

export async function totalSegments(): Promise<number> {
  const list = await load();
  return list.reduce((n, c) => n + c.segments.length, 0);
}
/** Test-only: drops the in-memory cache so a suite can start from empty storage. */
export function _resetCacheForTests(): void {
  cache = null;
}
