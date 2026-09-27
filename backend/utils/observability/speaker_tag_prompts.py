"""Privacy-safe instrumentation for speaker tag prompts.

Labels are closed enums only: prompt kind, answer, quality outcome, sample
outcome. Never names, transcript text, audio, embeddings, or ids. Quality is
measured from the user's own answers: an automatic label the user confirms or
rejects is a precision observation, and an unnamed voice the user names is a
recall miss. Both are biased (users answer only what we ask), so read them as
trends per kind, not as absolute accuracy.
"""

from prometheus_client import Counter

SPEAKER_TAG_PROMPT_REQUESTS = Counter(
    'omi_speaker_tag_prompt_requests_total',
    'Tag-prompt list requests by result status (ok, disabled, cooldown, no_candidates, recently_checked).',
    ['status'],
)
SPEAKER_TAG_PROMPTS_SERVED = Counter(
    'omi_speaker_tag_prompts_served_total',
    'Tag prompts returned to a client, by kind.',
    ['kind'],
)
SPEAKER_TAG_PROMPTS_SKIPPED = Counter(
    'omi_speaker_tag_prompts_skipped_total',
    'Candidate prompts excluded by stored-audio coverage or clip verification.',
    ['reason'],
)
SPEAKER_TAG_PROMPT_SETS = Counter(
    'omi_speaker_tag_prompt_sets_total',
    'Tag-prompt sets the client reported as shown or dismissed without an answer.',
    ['event'],
)
SPEAKER_TAG_PROMPT_ANSWERS = Counter(
    'omi_speaker_tag_prompt_answers_total',
    'Tag-prompt answers by prompt kind and answer.',
    ['kind', 'answer'],
)
SPEAKER_TAG_PROMPT_QUALITY = Counter(
    'omi_speaker_tag_prompt_quality_total',
    'Recognition quality observations derived from tag-prompt answers.',
    ['outcome'],
)
SPEAKER_TAG_PROMPT_VOICE_SAMPLES = Counter(
    'omi_speaker_tag_prompt_voice_samples_total',
    'Voice samples attempted from tag-prompt answers, by target and outcome.',
    ['target', 'outcome'],
)
VOICE_PROFILE_SETTING_CHANGES = Counter(
    'omi_voice_profile_setting_changes_total',
    'Voice-profile preference changes by setting, new value and surface.',
    ['setting', 'enabled', 'source'],
)
