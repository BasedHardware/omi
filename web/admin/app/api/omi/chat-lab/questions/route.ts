import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

const KNOWN_USER_UID = 'viUv7GtdoHXbK1UBCDlPuTDuPgJ2';
const MAX_QUESTION_LENGTH = 200;
const CONTEXT_TYPES = ['memories', 'conversations', 'screen', 'search', 'tasks'] as const;

type ContextType = (typeof CONTEXT_TYPES)[number];

interface QuestionEntry {
  text: string;
  context_type: ContextType;
  source: string;
  count?: number;
}

function inferContextType(text: string): ContextType {
  const lower = text.toLowerCase();
  if (lower.includes('remember') || lower.includes('memory') || lower.includes('recall')) return 'memories';
  if (lower.includes('conversation') || lower.includes('meeting') || lower.includes('said') || lower.includes('talked'))
    return 'conversations';
  if (lower.includes('screen') || lower.includes('looking at') || lower.includes('see on')) return 'screen';
  if (lower.includes('search') || lower.includes('find') || lower.includes('look up')) return 'search';
  if (lower.includes('task') || lower.includes('todo') || lower.includes('remind me to')) return 'tasks';
  return 'conversations';
}

function extractTopQuestions(
  messages: { text: string }[],
  source: string,
  limit: number = 5
): QuestionEntry[] {
  const freq = new Map<string, number>();

  for (const msg of messages) {
    const text = (msg.text || '').trim();
    if (!text || text.length > MAX_QUESTION_LENGTH) continue;
    const normalized = text.toLowerCase().replace(/[?!.]+$/, '').trim();
    if (!normalized) continue;
    freq.set(normalized, (freq.get(normalized) || 0) + 1);
  }

  const sorted = Array.from(freq.entries()).sort((a, b) => b[1] - a[1]).slice(0, limit);

  return sorted.map(([text, count]) => ({
    text,
    context_type: inferContextType(text),
    source,
    count,
  }));
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();

    // 1. Fetch messages from the known user (no compound index needed)
    const knownUserSnapshot = await db
      .collection('users')
      .doc(KNOWN_USER_UID)
      .collection('messages')
      .orderBy('created_at', 'desc')
      .limit(500)
      .get();

    const knownUserMessages = knownUserSnapshot.docs
      .map((doc) => doc.data())
      .filter((m) => m.sender === 'human') as { text: string }[];
    const yourQuestions = extractTopQuestions(knownUserMessages, KNOWN_USER_UID);

    // 2. Sample from a few other active users (avoid collection group index requirements)
    const usersSnap = await db.collection('users').limit(30).get();
    const otherUids = usersSnap.docs.map(d => d.id).filter(id => id !== KNOWN_USER_UID).slice(0, 20);

    const otherResults = await Promise.allSettled(
      otherUids.map((uid) =>
        db.collection('users').doc(uid).collection('messages')
          .orderBy('created_at', 'desc')
          .limit(100)
          .get()
      )
    );

    const otherMessages = otherResults
      .filter((r): r is PromiseFulfilledResult<FirebaseFirestore.QuerySnapshot> => r.status === 'fulfilled')
      .flatMap((r) => r.value.docs.map((doc) => doc.data()))
      .filter((m) => m.sender === 'human') as { text: string }[];

    const allUsersQuestions = extractTopQuestions(otherMessages, 'all_users');

    // 3. Check for curated questions
    const curatedSnapshot = await db
      .collection('admin')
      .doc('chat_lab')
      .collection('questions')
      .get();

    const curated = curatedSnapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    }));

    // If curated questions exist, return those; otherwise merge your + all users
    const questions = curated.length > 0
      ? curated.map((q: any, i: number) => ({ id: q.id || `q-${i}`, text: q.text, context_type: q.context_type || 'conversations' }))
      : [
          ...yourQuestions.slice(0, 5).map((q, i) => ({ id: `your-${i}`, text: q.text, context_type: q.context_type })),
          ...allUsersQuestions.slice(0, 5).map((q, i) => ({ id: `all-${i}`, text: q.text, context_type: q.context_type })),
        ];

    return NextResponse.json({
      questions,
      your_questions: yourQuestions,
      all_users_questions: allUsersQuestions,
    });
  } catch (error) {
    console.error('[Chat Lab] Error fetching questions:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { questions } = body;

    if (!Array.isArray(questions)) {
      return NextResponse.json({ error: 'questions must be an array' }, { status: 400 });
    }

    const db = getDb();
    const collRef = db.collection('admin').doc('chat_lab').collection('questions');

    // Clear existing curated questions
    const existing = await collRef.get();
    const batch = db.batch();
    existing.docs.forEach((doc) => batch.delete(doc.ref));

    // Add new curated questions
    for (const q of questions) {
      if (!q.text || !q.context_type) continue;
      const newDoc = collRef.doc();
      batch.set(newDoc, {
        text: q.text,
        context_type: q.context_type,
        updated_at: new Date().toISOString(),
        updated_by: authResult.uid,
      });
    }

    await batch.commit();

    return NextResponse.json({ saved: questions.length });
  } catch (error) {
    console.error('[Chat Lab] Error saving curated questions:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
