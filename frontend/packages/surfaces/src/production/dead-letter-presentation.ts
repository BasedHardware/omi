/**
 * What a dead-letter panel renders, and — the point of this module — what it
 * is STRUCTURALLY UNABLE to offer.
 *
 * ── THE TRAP THIS FILE EXISTS TO SPRING ────────────────────────────────────
 *
 * David signed the `stale_epoch` copy in person
 * (`DAVID-retention-and-refusal-copy.md` §2):
 *
 *     "We couldn't apply this change. Your edit is saved below — paste it back
 *      in to apply it now."
 *
 * and signed, in the same breath, that this surface must NOT grow a "Try
 * again" button. The two look contradictory until you read the mechanism. The
 * dead envelope carries the account epoch the op was authored under. The
 * account-epoch fence compares that stamp and refuses it — every time, forever,
 * by construction, because the epoch it names is behind and epochs only
 * advance. RE-APPLYING is a different act: a person retypes the content, which
 * mints a NEW op under the CURRENT epoch, and that is accepted normally. So the
 * copy asks for the one action that works.
 *
 * And it makes a "Try again" button look obvious to whoever touches this
 * surface next. The copy says "apply it now"; a button is the natural reading;
 * the button would resubmit the doomed envelope and fail silently for as long
 * as anyone kept pressing it. That is the defect this module is shaped to make
 * unrepresentable rather than merely discouraged: the affordance list is a
 * closed union with no resubmit member, so adding one is a typed change to a
 * file whose whole comment is about why you must not — and
 * `dead-letter-presentation.test.mjs` fails the moment the union grows a member
 * a panel could wire to a send.
 *
 * If a one-tap affordance is ever genuinely wanted, it CONSTRUCTS A NEW OP from
 * the payload. It does not resubmit the dead one. That is not a style
 * preference; it is the difference between an action that can succeed and one
 * that cannot.
 *
 * ── WHY THE SIGNED STRING IS CONDITIONAL ───────────────────────────────────
 *
 * "Your edit is saved below" is a promise about what is on the screen. A dead
 * letter journaled before `payload` existed has nothing to show, and one whose
 * payload does not parse has nothing readable. Rendering the signed string over
 * an empty panel would make an owner-signed sentence false — the exact failure
 * class the write taxonomy exists to prevent, arriving through the copy instead
 * of through the wire. So the signed string renders only when the payload
 * actually renders; otherwise the panel falls back to `dead.body`, which is
 * true in every case. No new copy is invented for the gap, because inventing
 * user-facing copy is not a delegate's call.
 *
 * The payload is read through `deadLetterPayload()` and never through a bare
 * `JSON.parse` — that accessor returns `null` instead of throwing, which has
 * already been caught once as the difference between a panel that degrades and
 * a panel that white-screens on an old journal entry.
 */

import { deadLetterPayload, type DeadLetter } from "@omi-core/contracts";

/**
 * Every action a dead letter may offer, as a closed union.
 *
 * There is exactly one, and adding a second is a deliberate act. In
 * particular there is no `"retry"`, no `"resend"`, and no `"apply"`: see the
 * header. `"discard"` is safe because the user's content is on screen and the
 * server-side copy (when the refusal preserved one) is unaffected by what the
 * client discards.
 */
export const DEAD_LETTER_AFFORDANCES = ["discard"] as const;

export type DeadLetterAffordance = (typeof DEAD_LETTER_AFFORDANCES)[number];

/** The catalog keys this surface may render. Both already exist and are signed or long-standing. */
export type DeadLetterMessageKey = "dead.body" | "dead.staleEpoch";

export interface DeadLetterView {
  readonly opId: string;
  /** The message key to render. Never interpolated, never server text. */
  readonly messageKey: DeadLetterMessageKey;
  /**
   * The user's own edit, verbatim, as the text the panel shows beneath the
   * message — `null` when there is nothing to show, in which case
   * `messageKey` is never the string that promises one.
   */
  readonly savedEdit: string | null;
  readonly affordances: readonly DeadLetterAffordance[];
}

/**
 * The user's edit as displayable text, or `null`.
 *
 * Pretty-printed JSON rather than a domain-aware rendering: this module serves
 * every writable domain, the payload IS the serialized op, and the ruling asks
 * for the payload to be rendered. A per-domain rendering is a product
 * improvement, not a correctness one, and it is not a delegate's call to design
 * it — what matters here is that the sentence "saved below" is true.
 */
export function deadLetterSavedEdit(letter: DeadLetter): string | null {
  const payload = deadLetterPayload(letter);
  if (payload === null) return null;
  try {
    const text = JSON.stringify(payload, null, 2);
    return text === undefined || text.trim() === "" ? null : text;
  } catch {
    // A payload that parsed but cannot re-serialize (a cycle cannot come from
    // JSON.parse, but a caller-constructed letter could carry one) is treated
    // exactly like an absent one: no promise is made about it.
    return null;
  }
}

/**
 * The single decision every dead-letter panel routes through.
 *
 * `stale_epoch` is the only reason with signed copy of its own; every other
 * permanent reason keeps the long-standing generic string, which is true of
 * all of them and claims nothing about a saved edit.
 */
export function deadLetterView(letter: DeadLetter): DeadLetterView {
  const savedEdit = deadLetterSavedEdit(letter);
  const messageKey: DeadLetterMessageKey =
    letter.failure.reason === "stale_epoch" && savedEdit !== null ? "dead.staleEpoch" : "dead.body";
  return {
    opId: letter.opId,
    messageKey,
    // The saved edit is shown only where the copy promises it. Rendering a
    // serialized op under the generic string would be new product behaviour on
    // outcomes nobody ruled about.
    savedEdit: messageKey === "dead.staleEpoch" ? savedEdit : null,
    affordances: DEAD_LETTER_AFFORDANCES,
  };
}
