"""Bind enrichment retry custody at the conversation-processing boundary.

Speaker reconstruction is also imported by the smaller batch worker image;
keep the full enrichment scheduler dependency out of that shared layer.
"""


def resolve_speakers_for_processing(uid, conversation):
    from utils.conversations import speaker_resolution
    from utils.conversations.final_pass_retry import enqueue

    return speaker_resolution.resolve_speakers_for_processing(
        uid, conversation, requeue_final_pass=lambda *args: enqueue(uid, conversation)
    )
