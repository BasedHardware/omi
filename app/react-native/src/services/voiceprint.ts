/**
 * Voiceprint enrollment + speaker labeling. Mirrors desktop/linux voiceprint.ts:
 * the first heard cluster is enrolled as "You"; later clusters become "Other N".
 */
const ENROLLED = 'enrolled_speaker';

export function createVoiceprint() {
  let enrolled: string | null = null;
  const others = new Map<string, number>();
  let otherCounter = 0;

  return {
    enroll(speaker: string) {
      if (!enrolled) enrolled = speaker;
    },
    clear() {
      enrolled = null;
      others.clear();
      otherCounter = 0;
    },
    labelForSpeaker(speaker: string): { label: string; isUser: boolean } {
      if (speaker === enrolled) return { label: 'You', isUser: true };
      if (!others.has(speaker)) {
        others.set(speaker, ++otherCounter);
      }
      return { label: `Other ${others.get(speaker)}`, isUser: false };
    },
    isEnrolled() {
      return enrolled !== null;
    },
  };
}

export type Voiceprint = ReturnType<typeof createVoiceprint>;
export { ENROLLED };
