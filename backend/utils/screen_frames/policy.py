"""Purpose registry for screen-frame egress.

The limits here live server-side, never in the request. A client cannot ask
for a bigger cap, a different model, or a looser policy version — it can only
name a purpose, and the server looks up everything else.
"""

from dataclasses import dataclass

from models.screen_frame import ScreenFrameEgressPurpose, ScreenFrameRetentionClass

# David's ruling, 2026-08-24: faces are INCLUDED. "Faces are the fastest way to remind a
# person what their meeting was about and who it was with."
#
# This supersedes the earlier conservative default, which rejected any recognisable face.
# The reasoning is worth keeping because it also changes what a good banner is: the point
# of a note's hero image is recall, and a participant's face carries more of that than any
# amount of the code or documents that dominate this user's capture.
#
# What did NOT change: a face does not make a frame publishable on its own. The frame still
# has to be meeting-relevant shared content, and every other reject reason still applies —
# a face in a medical portal, a banking screen, or a DM thread is rejected for those
# reasons, not for being a face. A personal photo library or a social feed is rejected as
# not meeting-relevant.
REJECT_IDENTIFIABLE_PERSONS = False


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
