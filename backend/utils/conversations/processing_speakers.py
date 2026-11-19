"""Bind enrichment retry custody at the conversation-processing boundary.

Speaker reconstruction is also imported by the smaller batch worker image;
keep the full enrichment scheduler dependency out of that shared layer.
"""


def resolve_speakers_for_processing(uid, conversation, *, on_persist):
    from utils.conversations import speaker_resolution

    if not speaker_resolution.resolution_enabled():
        return speaker_resolution.resolve_speakers_for_processing(uid, conversation)
    from utils.conversations.final_pass_retry import resolve_direct

    return resolve_direct(
        uid, conversation, resolve=speaker_resolution.resolve_speakers_for_processing, on_persist=on_persist
    )
