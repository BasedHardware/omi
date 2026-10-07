import { searchLocal, knownSpeakers, type SearchHit } from './localConversations';

/**
 * The local assistant: answers from what is on the device.
 *
 * IMPORTANT — what this is and is not. The "brain" is MiniLM-L6-v2, a sentence
 * *embedder*. It can say which of three buckets an utterance is nearest, and it
 * can tell that "brown bread" and "white bread" are on a similar topic. It
 * cannot generate a sentence. So this is retrieval, not generation, and the
 * difference is visible in the outputs: every answer here is something someone
 * actually said, quoted, or an explicit "I can't do that yet".
 *
 * That is still genuinely useful, and it is honest. A generative answer invented
 * from nothing is worse than a refusal when the question was "what did marco say".
 *
 * Where generation would be required -- "what is the weather", "where am I" -- the
 * answer says so instead of confabulating. Those want the server agent, which
 * needs a session.
 */

export interface AssistantAnswer {
  /** Text to show and, once TTS is wired to a session, to speak. */
  text: string;
  /** What kind of answer this is, so the UI can label its confidence. */
  kind: 'quote' | 'summary' | 'capability' | 'unsupported' | 'empty';
  /** Supporting evidence, when there is any. */
  hits: SearchHit[];
  /** Speakers the user could filter by, when the question implied one. */
  speakerHint?: string;
}

const NO_CONTEXT =
  "I don't have anything recorded that covers that yet. Capture a conversation first, and I can pull the exact words back out.";

const CANNOT_GENERATE =
  "That needs a live answer rather than something you said. Weather, your location, and anything else that needs the internet aren't things I can answer on-device yet — sign in and I can pass it to the server.";

/**
 * Answers `text` using only local storage.
 *
 * Deliberately narrow: recall from recordings, and a clear refusal otherwise.
 */
export async function answerLocally(text: string): Promise<AssistantAnswer> {
  const q = text.trim();
  if (!q) return { text: 'Ask me something.', kind: 'empty', hits: [] };

  // "what did X say about Y" and "did X say Y" both name a speaker. Pulling the
  // name out is what makes the speaker filter usable when nobody has been assigned
  // a real identity yet.
  const speakers = await knownSpeakers();
  const speaker = detectSpeaker(q, speakers);
  const topic = stripQuestion(q, speaker);

  const wantsRecall =
    /\b(say|said|tell me|what did|what does|what was|did .* say|recall|remember|when did)\b/i.test(
      q
    );

  if (topic.length < 2) {
    return {
      text:
        'Try asking about something that was said, for example: "what did marco say about bread".',
      kind: 'capability',
      hits: [],
    };
  }

  const hits = await searchLocal(topic, { speaker, limit: 6 });

  if (hits.length === 0) {
    if (wantsRecall) {
      return {
        text: speaker
          ? `Nothing recorded matching "${topic}" from ${speaker}.`
          : `Nothing recorded matching "${topic}".`,
        kind: 'empty',
        hits: [],
        speakerHint: speaker,
      };
    }
    return { text: CANNOT_GENERATE, kind: 'unsupported', hits: [], speakerHint: speaker };
  }

  // hits.length was just checked, but noUncheckedIndexedAccess still cannot see
  // that, and the alternative is a non-null assertion on something a refactor
  // could break silently.
  const best = hits[0];
  if (!best) return { text: NO_CONTEXT, kind: 'empty', hits: [] };
  const strongEnough = best.score >= 0.5;

  if (!strongEnough) {
    // Weak matches are worse than none: a wrong quote about what someone said is
    // the worst failure mode this assistant has.
    return {
      text: `Nothing here clearly matches "${topic}". Closest was: "${best.text}" — was that what you meant?`,
      kind: 'empty',
      hits,
      speakerHint: speaker,
    };
  }

  if (wantsRecall) {
    return {
      text: hits
        .slice(0, 3)
        .map((h) => `${h.speaker}: "${h.text}"`)
        .join('\n'),
      kind: 'quote',
      hits,
      speakerHint: speaker,
    };
  }

  return {
    text: `Closest thing you said about "${topic}":\n\n${hits
      .slice(0, 3)
      .map((h) => `${h.speaker}: "${h.text}"`)
      .join('\n')}`,
    kind: 'summary',
    hits,
    speakerHint: speaker,
  };
}

/**
 * Finds a speaker name in the question that matches a known label.
 *
 * With a real session the backend can filter on a real speaker_id. Locally the
 * only labels are the voiceprint's "You"/"Other 1", so a name like "marco" only
 * matches when a segment is literally labelled that. This returns the label when
 * one matches and undefined otherwise, and the caller reports which label it
 * used, so a miss is visible rather than silently searching everything.
 */
export function detectSpeaker(query: string, known: string[]): string | undefined {
  const q = query.toLowerCase();
  for (const s of known) {
    const n = s.toLowerCase();
    if (n.length < 2) continue;
    if (q.includes(n)) return s;
  }
  return undefined;
}

/** Removes the question scaffolding, leaving the topic to search for. */
export function stripQuestion(query: string, speaker?: string): string {
  let q = query.trim();

  // Opening scaffolding: "what did ...", "did ...", "tell me about ...".
  for (const p of [
    /^\s*what\s+(?:did|does|do|was|were)\s+/i,
    /^\s*what\s+is\s+/i,
    /^\s*when\s+(?:did|was|were)\s+/i,
    /^\s*do\s+(?:you|i|we)\s+(?:know|remember)\s+/i,
    /^\s*did\s+/i,
    /^\s*(?:can you|could you)\s+(?:remind me to\s+)?(?:tell me|recall)\s+/i,
    /^\s*(?:tell me|recall|remember)\s+(?:what|about|that)\s+/i,
    /^\s*(?:tell me about|remind me (?:what|about))\s+/i,
    /^\s*(?:have i|did i)\s+(?:said|told you)\s+/i,
  ]) {
    q = q.replace(p, '');
  }

  // The important one: "<name> say|says|said|told me <rest>". Stripping this is
  // what turns "what did marco say about bread" into "bread". Without it the
  // topic kept the name and the verb, neither of which appears in what was
  // actually said, so term coverage collapsed and every question looked like a
  // miss. A test caught exactly that.
  q = q.replace(/\b[A-Za-z0-9_']+\s+(?:say|says|said|tell me|told me)\b/gi, ' ');

  if (speaker) {
    const escaped = speaker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    q = q.replace(new RegExp(`\\b${escaped}\\b`, 'ig'), ' ');
  }

  q = q
    .replace(/\babout\b/gi, ' ')
    .replace(/\b(?:that|the thing)\b/gi, ' ')
    .replace(/[?!.,]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return q;
}
