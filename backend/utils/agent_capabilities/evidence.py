"""Session evidence snapshots; roles never enter product fingerprints."""


class EvidenceRecords(dict):
    """Roles live outside storage snapshots so Review fingerprints stay intact."""

    def __init__(self, records=(), *, targets=None):
        super().__init__(records)
        self.targets = set(self if targets is None else targets)


# An allowlist: a voice field added to person rows later cannot reach a model by default.
PERSON_MODEL_FIELDS = (
    'id',
    'entity_id',
    'type',
    'name',
    'aliases',
    'subtitle',
    'role',
    'organization_id',
    'is_dismissed',
    'user_confirmed',
    'is_user_created',
    'pinned',
    'pinned_at',
    'confidence',
    'confidence_reasons',
    'label_evidence',
    'labels_to_confirm',
    'last_labeled_at',
    'conversation_count',
    'auto_conversation_count',
    'last_heard_at',
    'talk_seconds',
    'created_at',
    'updated_at',
)
VOICE_MARKERS = ('speaker_embedding', 'speech_samples', 'person_voice_base', 'person_voice_confirmations')


def model_view(ref, row):
    """What a model may see of a record; staging keeps the full row to judge protection."""
    if not ref.startswith('people/') or not isinstance(row, dict):
        return row
    kept = {key: row[key] for key in PERSON_MODEL_FIELDS if key in row}
    if any(row.get(key) for key in VOICE_MARKERS):
        kept['has_voice_profile'] = True
    return kept
