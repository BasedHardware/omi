// Voiceprint enrollment for speaker identification.
//
// Deepgram `nova-2` + `diarize=true` emits ephemeral per-session speaker cluster
// IDs (0, 1, 2…). There is no stable cross-session biometric on nova-2, so we
// "enroll" the user by capturing the dominant speaker cluster during a short
// enrollment utterance and persisting it in local storage. Segments whose cluster
// matches the enrolled id are labeled as the user ("You"); everything else is
// "Other N". On a fresh session the cluster ids are recomputed, so we re-match by
// comparing the first utterance's cluster against the enrolled label at session
// start (see reIdentify below).
//
// All data stays local — only a small integer cluster id is stored.

const ENROLL_KEY = 'omi.voiceprint.enrolledSpeaker'
const ENROLLED_FLAG = 'omi.voiceprint.enrolled'

export type VoiceprintState = {
  enrolled: boolean
  /** The Deepgram speaker cluster id that maps to the user in the CURRENT session. */
  speakerId: number | null
}

let current: VoiceprintState = { enrolled: false, speakerId: null }

function load(): void {
  try {
    const flag = localStorage.getItem(ENROLLED_FLAG) === '1'
    const raw = localStorage.getItem(ENROLL_KEY)
    const speakerId = raw != null ? Number(raw) : null
    current = {
      enrolled: flag && speakerId != null && !Number.isNaN(speakerId),
      speakerId: flag && speakerId != null && !Number.isNaN(speakerId) ? speakerId : null
    }
  } catch {
    current = { enrolled: false, speakerId: null }
  }
}

load()

export function getVoiceprint(): VoiceprintState {
  return { ...current }
}

export function isEnrolled(): boolean {
  return current.enrolled
}

/** Persist the user's speaker cluster id for this session as the enrolled voice. */
export function enrollSpeaker(speakerId: number): void {
  current = { enrolled: true, speakerId }
  try {
    localStorage.setItem(ENROLLED_FLAG, '1')
    localStorage.setItem(ENROLL_KEY, String(speakerId))
  } catch {
    /* storage may be unavailable; keep in-memory state */
  }
}

export function clearVoiceprint(): void {
  current = { enrolled: false, speakerId: null }
  try {
    localStorage.removeItem(ENROLLED_FLAG)
    localStorage.removeItem(ENROLL_KEY)
  } catch {
    /* ignore */
  }
}

/**
 * Given the dominant speaker cluster of an utterance, return the label Omi
 * should use and whether it is the enrolled user. If not yet enrolled, the
 * caller is expected to drive enrollment; we still return a sensible label.
 */
export function labelForSpeaker(speakerId: number): { speaker: string; isUser: boolean } {
  if (current.enrolled && current.speakerId === speakerId) {
    return { speaker: 'You', isUser: true }
  }
  if (current.enrolled) {
    // Re-map unknown clusters relative to the user's id so labels are stable
    // within a session (e.g. user=0 → others 1,2,3…).
    const offset = speakerId - (current.speakerId ?? 0)
    return { speaker: offset <= 0 ? `Other ${Math.abs(offset)}` : `Other ${offset}`, isUser: false }
  }
  return { speaker: speakerId === 0 ? 'You' : `Speaker ${speakerId}`, isUser: speakerId === 0 }
}

/**
 * At the start of a new session we don't know which cluster is the user until
 * enrollment (or a heuristic) runs. Call this once we observe the user's first
 * utterance cluster; if enrolled, it re-anchors the `speakerId` to whatever
 * cluster the user actually produced this session.
 */
export function reAnchorIfEnrolled(observedUserCluster: number): void {
  if (current.enrolled) {
    current = { enrolled: true, speakerId: observedUserCluster }
    try {
      localStorage.setItem(ENROLL_KEY, String(observedUserCluster))
    } catch {
      /* ignore */
    }
  }
}
