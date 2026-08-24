"""Purpose registry for screen-frame egress.

The limits here live server-side, never in the request. A client cannot ask
for a bigger cap, a different model, or a looser policy version — it can only
name a purpose, and the server looks up everything else.
"""

from dataclasses import dataclass

from models.screen_frame import ScreenFrameEgressPurpose, ScreenFrameRetentionClass

# ASSUMPTION flagged for David (contract §4, "Face policy"): a frame showing a
# recognisable third-party face is rejected outright, never published. A
# meeting participant did not consent to appearing in someone else's stored
# note, and this is the reversible direction — we can loosen this later, we
# cannot un-store a person's face. David has not yet ruled on this; flipping
# it is a one-line change here once he does.
REJECT_IDENTIFIABLE_PERSONS = True


@dataclass(frozen=True)
class ScreenFramePurposePolicy:
    subject_kind: str
    retention: ScreenFrameRetentionClass
    max_candidates: int
    max_persisted: int  # one banner + six strip
    setting_key: str
    share_default: bool
    model: str
    policy_version: str
    prompt_version: str


SCREEN_FRAME_PURPOSES: dict[ScreenFrameEgressPurpose, ScreenFramePurposePolicy] = {
    ScreenFrameEgressPurpose.MEETING_NOTE_V1: ScreenFramePurposePolicy(
        subject_kind="conversation",
        retention=ScreenFrameRetentionClass.WITH_SUBJECT,
        max_candidates=8,
        max_persisted=7,
        setting_key="meeting_note_screenshots_enabled",
        share_default=True,
        model="gemini-2.5-flash-lite",
        policy_version="meeting_note_privacy.v1",
        prompt_version="meeting_note_frame_judge.v1",
    )
}


def get_purpose_policy(purpose: str) -> ScreenFramePurposePolicy | None:
    """Look up the server-side policy for a purpose string from the wire.

    Returns None for any purpose not in the registry — callers must treat
    that as an unknown/unsupported purpose (400), never fall back to a
    default policy.
    """
    try:
        key = ScreenFrameEgressPurpose(purpose)
    except ValueError:
        return None
    return SCREEN_FRAME_PURPOSES.get(key)
