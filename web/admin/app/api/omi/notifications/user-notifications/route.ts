import { NextRequest, NextResponse } from 'next/server';
import { getDb, getAdminAuth } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
import crypto from 'crypto';
import zlib from 'zlib';

export const dynamic = 'force-dynamic';

function deriveKey(uid: string): Buffer {
  const secret = process.env.ENCRYPTION_SECRET;
  if (!secret) throw new Error('ENCRYPTION_SECRET not set');
  return Buffer.from(
    crypto.hkdfSync('sha256', Buffer.from(secret, 'utf-8'), Buffer.from(uid, 'utf-8'), Buffer.from('user-data-encryption'), 32)
  );
}

// Decrypt text encrypted by the backend (AES-256-GCM with HKDF-derived key)
function decryptText(encryptedB64: string, uid: string): string {
  const secret = process.env.ENCRYPTION_SECRET;
  if (!secret || !encryptedB64) return encryptedB64;

  try {
    const key = deriveKey(uid);
    const payload = Buffer.from(encryptedB64, 'base64');
    const nonce = payload.subarray(0, 12);
    const tag = payload.subarray(payload.length - 16);
    const ciphertext = payload.subarray(12, payload.length - 16);

    const decipher = crypto.createDecipheriv('aes-256-gcm', key, nonce);
    decipher.setAuthTag(tag);
    const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    return decrypted.toString('utf-8');
  } catch {
    return encryptedB64;
  }
}

// Decompress/decrypt transcript_segments stored in Firestore
// Backend stores them as: compressed bytes (standard), encrypted+compressed string (enhanced), or raw array (legacy)
function extractTranscriptSegments(convo: any, uid: string): any[] {
  const raw = convo.transcript_segments;
  if (!raw) return [];

  // Legacy: already an array
  if (Array.isArray(raw)) return raw;

  const isCompressed = convo.transcript_segments_compressed === true;
  const isEncrypted = convo.data_protection_level === 'enhanced';

  try {
    if (isEncrypted && typeof raw === 'string') {
      // Enhanced: base64(nonce + AES-GCM(hex(zlib(json))))
      const decryptedHex = decryptText(raw, uid);
      if (isCompressed) {
        const compressedBytes = Buffer.from(decryptedHex, 'hex');
        const decompressed = zlib.inflateSync(compressedBytes).toString('utf-8');
        return JSON.parse(decompressed);
      }
      return JSON.parse(decryptedHex);
    }

    if (isCompressed && Buffer.isBuffer(raw)) {
      // Standard: zlib-compressed bytes
      const decompressed = zlib.inflateSync(raw).toString('utf-8');
      return JSON.parse(decompressed);
    }

    // Firestore may also return Uint8Array for bytes fields
    if (isCompressed && raw instanceof Uint8Array) {
      const decompressed = zlib.inflateSync(Buffer.from(raw)).toString('utf-8');
      return JSON.parse(decompressed);
    }
  } catch (e) {
    console.error('Failed to extract transcript_segments:', e);
  }

  return [];
}

function buildConvoContext(convo: any, id: string, uid: string) {
  const title = convo.structured?.title || convo.title || '';
  const overview = convo.structured?.overview || convo.overview || '';

  let transcript = '';
  const segments = extractTranscriptSegments(convo, uid);
  if (segments.length > 0) {
    const sampled = segments.length > 50
      ? [...segments.slice(0, 25), ...segments.slice(-25)]
      : segments;
    transcript = sampled
      .map((seg: any) => {
        const segText = seg.text || '';
        const speaker = seg.is_user ? 'User' : 'Other';
        return `[${speaker}]: ${segText}`;
      })
      .filter((line: string) => line.length > 10)
      .join('\n');
  }

  return { id, title, overview, transcript };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const uid = request.nextUrl.searchParams.get('uid');
    if (!uid || uid.length < 10) {
      return NextResponse.json({ error: 'Valid uid parameter required' }, { status: 400 });
    }

    const userRef = db.collection('users').doc(uid);

    // 1. Fetch proactive notifications from ALL sources (built-in mentor + marketplace apps)
    // Proactive notifications: sender='ai', no chat_session_id, has plugin_id/app_id
    const messagesSnap = await userRef
      .collection('messages')
      .orderBy('created_at', 'desc')
      .limit(200)
      .get();

    const conversationIds = new Set<string>();
    const rawMessages: any[] = [];
    for (const doc of messagesSnap.docs) {
      if (rawMessages.length >= 20) break;
      const data = doc.data();
      // Skip chat messages
      if (data.chat_session_id) continue;
      // Only AI-sent messages
      if (data.sender && data.sender !== 'ai') continue;
      // Must have an app/plugin source (skip desktop chat messages which have null plugin_id)
      if (!data.plugin_id && !data.app_id) continue;
      for (const memId of data.memories_id || []) {
        conversationIds.add(memId);
      }
      rawMessages.push({ id: doc.id, ...data });
    }

    // 2. Fetch recent conversations (sorted by time) to match with notifications by timestamp
    //    memories_id is typically empty for mentor notifications, so we match by time instead
    const recentConvosSnap = await userRef
      .collection('conversations')
      .orderBy('created_at', 'desc')
      .limit(50)
      .get();

    const allConversations: { id: string; data: any; createdAt: Date }[] = [];
    for (const doc of recentConvosSnap.docs) {
      const data = doc.data();
      const createdAt = data.created_at?.toDate?.() ?? (data.created_at ? new Date(data.created_at) : new Date(0));
      allConversations.push({ id: doc.id, data, createdAt });
    }

    // Also batch-fetch any explicitly linked conversations (in case memories_id is populated)
    const conversations: Record<string, any> = {};
    if (conversationIds.size > 0) {
      const convoRef = userRef.collection('conversations');
      const docRefs = Array.from(conversationIds).map((id) => convoRef.doc(id));
      const docs = await db.getAll(...docRefs);
      for (const doc of docs) {
        if (doc.exists) {
          conversations[doc.id] = doc.data()!;
        }
      }
    }

    // 3. Fetch user memories (split into generated vs manually_added)
    const memoriesSnap = await userRef.collection('memories').limit(1000).get();

    const generatedMemories: string[] = [];
    const manualMemories: string[] = [];
    for (const doc of memoriesSnap.docs) {
      const data = doc.data();
      if (data.deleted === true) continue;
      const text = data.structured?.content || data.content || '';
      if (!text) continue;
      if (data.manually_added === true) {
        manualMemories.push(text);
      } else {
        generatedMemories.push(text);
      }
    }

    // 4. Fetch active goals
    const goalsSnap = await userRef
      .collection('goals')
      .where('is_active', '==', true)
      .limit(3)
      .get();

    const goals = goalsSnap.docs.map((doc: FirebaseFirestore.QueryDocumentSnapshot) => {
      const data = doc.data();
      return {
        title: data.title || '',
        description: data.description || '',
        checkpoints: (data.checkpoints || []).map((cp: any) => cp.title || cp.description || ''),
      };
    });

    // 5. Get user name and notification frequency
    let userName = 'User';
    try {
      const userRecord = await getAdminAuth().getUser(uid);
      userName = userRecord.displayName || 'User';
    } catch {
      // User may not exist in Auth
    }

    const userDoc = await userRef.get();
    const notificationFrequency = userDoc.exists ? (userDoc.data()?.mentor_notification_frequency ?? 3) : 3;

    // 6. Format user_facts matching backend pattern
    let userFacts = `you already know the following facts about ${userName}: \n${generatedMemories.map((m, i) => `${i + 1}. ${m}`).join('\n')}.`;
    if (manualMemories.length > 0) {
      userFacts += `\n\n${userName} also shared the following about self: \n${manualMemories.map((m, i) => `${i + 1}. ${m}`).join('\n')}`;
    }
    userFacts += '\n';

    // 7. Format notifications (decrypt if encrypted)
    const notifications = rawMessages.map((msg: any) => {
      const createdAt = msg.created_at?.toDate?.() ?? (msg.created_at ? new Date(msg.created_at) : new Date());

      let text = msg.text || '';
      if (msg.data_protection_level === 'enhanced' && text) {
        text = decryptText(text, uid);
      }

      // Get linked conversation context with transcript
      let linkedConversations = (msg.memories_id || [])
        .filter((id: string) => conversations[id])
        .map((id: string) => buildConvoContext(conversations[id], id, uid));

      // If no linked conversations (memories_id empty), find by timestamp
      if (linkedConversations.length === 0 && allConversations.length > 0) {
        const notifTime = createdAt.getTime();
        // Find the conversation closest to (and before/around) the notification time
        // A notification is sent during or shortly after a conversation
        let bestMatch: { id: string; data: any } | null = null;
        let bestDiff = Infinity;
        for (const convo of allConversations) {
          const diff = notifTime - convo.createdAt.getTime();
          // Notification should be within 30 min after conversation start
          if (diff >= -60000 && diff < 30 * 60 * 1000 && Math.abs(diff) < bestDiff) {
            bestDiff = Math.abs(diff);
            bestMatch = convo;
          }
        }
        if (bestMatch) {
          linkedConversations = [buildConvoContext(bestMatch.data, bestMatch.id, uid)];
        }
      }

      return {
        id: msg.id,
        text,
        created_at: createdAt.toISOString(),
        sender: msg.sender || 'ai',
        plugin_id: msg.plugin_id || msg.app_id || null,
        conversation_context: linkedConversations,
      };
    });

    // 8. Format goals text
    const goalsText = goals.length > 0
      ? goals.map((g: any, i: number) => {
          let text = `${i + 1}. ${g.title}`;
          if (g.description) text += `: ${g.description}`;
          if (g.checkpoints.length > 0) text += `\n   Checkpoints: ${g.checkpoints.join(', ')}`;
          return text;
        }).join('\n')
      : 'No active goals set.';

    return NextResponse.json({
      notifications,
      user_context: {
        user_name: userName,
        user_facts: userFacts,
        goals: goalsText,
        notification_frequency: notificationFrequency,
      },
    });
  } catch (error: any) {
    console.error('Error fetching user notifications:', error);
    return NextResponse.json(
      { error: `Failed to fetch user notifications: ${error.message}` },
      { status: 500 }
    );
  }
}
