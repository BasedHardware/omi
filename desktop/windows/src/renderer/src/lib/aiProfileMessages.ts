// Plain-English lines for the AI-profile Settings card. The main-process reader
// reports failures as an AiProfileErrorCode (one per backend status the contract
// names: 402 / 409 / 422 / 502, plus auth, rate-limit and network); this turns
// each into a line the user can act on. Never a raw Error string — it can echo a
// backend body.
import type { AiProfileErrorCode } from '../../../shared/types'

export type AiProfileAction = 'load' | 'generate' | 'save' | 'delete'

export const AI_PROFILE_FALLBACK: Record<AiProfileAction, string> = {
  load: "Couldn't load your profile. Try again later.",
  generate: "Couldn't generate a profile right now. Make sure you're signed in and try again.",
  save: "Couldn't save your changes. Try again.",
  delete: "Couldn't delete the profile. Try again."
}

/** Plain-English line for a failed profile call. Never a raw Error string (it can
 *  echo a backend body). */
export function aiProfileErrorMessage(code: AiProfileErrorCode, action: AiProfileAction): string {
  switch (code) {
    case 'not_signed_in':
    case 'auth_expired':
      return 'Sign in to Omi again, then try again.'
    case 'usage_exhausted':
      return "You've reached your plan's AI usage limit, so Omi can't build a new profile right now. Your current profile is unchanged."
    case 'in_progress':
      return 'Omi is already updating your profile. Check back in a minute.'
    case 'insufficient_data':
      return "Omi doesn't know enough about you yet. Keep using Omi and try again later."
    case 'synthesis_failed':
      return "Omi couldn't build your profile this time. Try again in a few minutes."
    case 'rate_limited':
      return 'Too many requests. Wait a moment and try again.'
    case 'invalid_edit':
      return "The profile can't be empty or longer than 10,000 characters."
    case 'network':
      return "Couldn't reach Omi. Check your connection and try again."
    default:
      return AI_PROFILE_FALLBACK[action]
  }
}
