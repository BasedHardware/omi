import type { StoredConversation, StoredSegment } from '../localConversations';
import type { EvidenceRef, ExtractiveSummary, LocalMemory, LocalTask } from './types';

function nowMs() {
  return Date.now();
}
function id(prefix: string) {
  return `${prefix}_${nowMs().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
function evForSeg(c: StoredConversation, s: StoredSegment): EvidenceRef {
  return { conversationId: c.id, segmentId: s.id, text: s.text, speaker: s.speaker, startedAt: s.startedAt };
}
function uniq<T>(arr: T[]): T[] {
  return Array.from(new Set(arr));
}

const STOP = new Set(['the','a','an','and','or','but','is','are','was','were','be','to','of','in','on','at','for','with','it','that','this','i','you','we','they','me','my','your','so','have','had','has','do','did','does','can','could','would','should','just','about','like','yeah','ok','okay','um','uh']);

function tokenize(text: string): string[] {
  return text.toLowerCase().replace(/[^a-z0-9\s']/g, ' ').split(/\s+/).filter((t) => t.length > 2 && !STOP.has(t));
}

export function extractiveSummarize(conversation: StoredConversation): ExtractiveSummary {
  const segs = conversation.segments.filter((s) => s.text.trim());
  const freq = new Map<string, number>();
  for (const s of segs) for (const t of tokenize(s.text)) freq.set(t, (freq.get(t) ?? 0) + 1);

  const scored = segs.map((s, idx) => {
    const toks = tokenize(s.text);
    let score = toks.reduce((acc, t) => acc + (freq.get(t) ?? 0), 0);
    if (/\b(decide|decided|decision|agreed|will|plan|next)\b/i.test(s.text)) score += 6;
    if (/\b(need to|should|todo|task|remind|remember|follow up)\b/i.test(s.text)) score += 5;
    if (s.isUser) score += 1;
    score += Math.max(0, 2 - idx * 0.05);
    return { s, score };
  }).sort((a, b) => b.score - a.score);

  const highlights = uniq(scored.slice(0, 4).map((x) => x.s.text.trim())).slice(0, 4);
  const decisions = uniq(
    segs.filter((s) => /\b(decide|decided|decision|agreed|let's|we will|i will|plan to)\b/i.test(s.text)).map((s) => s.text.trim())
  ).slice(0, 4);
  const actionables = uniq(
    segs.filter((s) => /\b(need to|should|must|todo|task|remind me|follow up|i'll|i will|we need)\b/i.test(s.text)).map((s) => s.text.trim())
  ).slice(0, 5);
  const topicCounts = Array.from(freq.entries()).sort((a, b) => b[1] - a[1]);
  const topics = topicCounts.slice(0, 6).map(([t]) => t);

  const evidence: EvidenceRef[] = scored.slice(0, 6).map((x) => evForSeg(conversation, x.s));
  return {
    id: `sum_${conversation.id}`,
    conversationId: conversation.id,
    createdAt: nowMs(),
    highlights,
    decisions,
    actionables,
    topics,
    evidence,
  };
}

export function extractMemories(
  conversation: StoredConversation,
  summary?: Pick<ExtractiveSummary, 'highlights' | 'decisions' | 'actionables' | 'evidence'>
): LocalMemory[] {
  const out: LocalMemory[] = [];
  const seen = new Set<string>();

  const add = (kind: LocalMemory['kind'], text: string, confidence: number, evidence: EvidenceRef[]) => {
    const clean = text.trim();
    if (clean.length < 8) return;
    const key = `${kind}|${clean.toLowerCase().replace(/\s+/g, ' ').slice(0, 80)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      id: id('mem'),
      kind,
      text: clean,
      createdAt: nowMs(),
      updatedAt: nowMs(),
      confidence,
      status: 'active',
      evidence: evidence.length ? evidence.slice(0, 3) : [{ conversationId: conversation.id, startedAt: conversation.startedAt }],
      tags: tokenize(clean).slice(0, 5),
    });
  };

  // Prefer summary-derived memories so they stay scoped to this conversation's takeaways.
  const summaryItems = summary
    ? [
        ...summary.decisions.map((t) => ({ text: t, base: 'commitment' as const })),
        ...summary.actionables.map((t) => ({ text: t, base: 'commitment' as const })),
        ...summary.highlights.map((t) => ({ text: t, base: 'fact' as const })),
      ]
    : [];

  for (const item of summaryItems) {
    const lower = item.text.toLowerCase();
    let kind: LocalMemory['kind'] = item.base;
    let confidence = 0.72;
    if (/\b(prefer|like|love|favorite|hate|don't like)\b/.test(lower)) {
      kind = 'preference'; confidence = 0.76;
    } else if (/\b(always|usually|often|routine|every day|every morning|every week)\b/.test(lower)) {
      kind = 'routine'; confidence = 0.73;
    } else if (/\b(will|i'll|agreed|decided|plan to|need to|remind)\b/.test(lower)) {
      kind = 'commitment'; confidence = 0.74;
    } else if (/\b(i am|i'm|my name|i work|i live|i have)\b/.test(lower)) {
      kind = 'fact'; confidence = 0.68;
    }
    add(kind, item.text, confidence, summary?.evidence ?? []);
  }

  // Supplement with clear user-stated signals from the same conversation when needed.
  if (out.length < 4) {
    for (const s of conversation.segments) {
      const text = s.text.trim();
      if (text.length < 8) continue;
      const lower = text.toLowerCase();
      if (/\b(i prefer|i like|i love|my favorite|i usually prefer)\b/.test(lower)) add('preference', text, 0.76, [evForSeg(conversation, s)]);
      else if (/\b(i (always|usually|often|every day|every morning|every week)|my routine)\b/.test(lower)) add('routine', text, 0.72, [evForSeg(conversation, s)]);
      else if (/\b(i promised|i committed|i will|i'll|we agreed|i need to remember)\b/.test(lower)) add('commitment', text, 0.7, [evForSeg(conversation, s)]);
      if (out.length >= 8) break;
    }
  }

  return out.slice(0, 10);
}

function parseMinutesFromNow(text: string): number | undefined {
  const m = text.match(/\bin\s+(\d+)\s*(min|mins|minute|minutes|h|hr|hour|hours)\b/i);
  const n = m ? Number.parseInt(m[1] ?? '', 10) : NaN;
  if (!m || Number.isNaN(n)) return undefined;
  return /h/i.test(m[2] ?? '') ? n * 60 : n;
}

export function extractTasks(
  conversation: StoredConversation,
  summary?: Pick<ExtractiveSummary, 'actionables' | 'decisions' | 'evidence'>
): LocalTask[] {
  const out: LocalTask[] = [];
  const seen = new Set<string>();

  const addTask = (text: string, evidence: EvidenceRef[], isReminderHint = false) => {
    const raw = text.trim();
    if (raw.length < 3) return;
    const lower = raw.toLowerCase();
    const isReminder = isReminderHint || /\b(remind me|set a reminder|don't forget|remember to)\b/.test(lower);
    let title = raw
      .replace(/^.*?\b(remind me to|remind me|set a reminder to|remember to|i need to|we need to|i should|i must|follow up on|follow up)\b[:\s-]*/i, '')
      .replace(/\bin\s+\d+\s*(min|mins|minute|minutes|h|hr|hour|hours)\b.*$/i, '')
      .trim();
    if (!title) title = raw;
    title = title.replace(/[.?!]+$/, '').trim();
    if (title.length < 3) return;
    const key = title.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    const minutes = parseMinutesFromNow(raw);
    const dueAt = minutes ? nowMs() + minutes * 60_000 : null;
    out.push({
      id: id('task'),
      title: title.slice(0, 120),
      kind: isReminder ? 'reminder' : 'task',
      createdAt: nowMs(),
      updatedAt: nowMs(),
      dueAt,
      remindAt: dueAt,
      status: 'open',
      source: conversation.source,
      evidence: evidence.length ? evidence.slice(0, 3) : [{ conversationId: conversation.id, startedAt: conversation.startedAt }],
    });
  };

  // Prefer actionables identified in the conversation's summary (scoped to this session).
  if (summary) {
    for (const item of summary.actionables) addTask(item, summary.evidence);
    for (const item of summary.decisions) {
      if (/\b(will|need to|should|follow up|remind)\b/i.test(item)) addTask(item, summary.evidence);
    }
  }

  // Fallback/supplement: explicit task/reminder phrasing in this conversation.
  if (out.length < 3) {
    for (const s of conversation.segments) {
      const text = s.text.trim();
      const lower = text.toLowerCase();
      const isReminder = /\b(remind me|set a reminder|don't forget|remember to)\b/.test(lower);
      const isTask = isReminder || /\b(need to|i should|i must|todo|task|follow up|let's|we need to)\b/.test(lower);
      if (!isTask) continue;
      addTask(text, [evForSeg(conversation, s)], isReminder);
      if (out.length >= 8) break;
    }
  }

  return out.slice(0, 8);
}
