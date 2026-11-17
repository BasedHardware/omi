"""Customer follow-up writer scope and existing private playback persistence.

The scope holds context only. It never holds a SQL pool slot or owner guard
across bridge, audio or Firestore I/O; legacy stores retain their no-op scope.
Audio publication policy is unchanged and is not a G2 C4 sink qualification.
"""

from contextlib import nullcontext
from functools import wraps

from google.api_core.exceptions import NotFound

from utils.batch_pipeline import artifact_missing
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.contracts import WorkItem


def writer_scope(store):
    """Legacy structural stores have no binding; explicit class bindings prevail.

    Inspect the class protocol so dynamic metadata/Mock attributes cannot be
    mistaken for an installed coordinator. An installed scope never falls back
    when its construction or body fails.
    """
    factory = getattr(type(store), 'writer_scope', None)
    return factory(store) if factory is not None else nullcontext()


def customer_writer(method):
    @wraps(method)
    def scoped(self, *args, **kwargs):
        # Context only: no SQL pool slot or owner lock spans follow-up I/O.
        with writer_scope(self.store):
            return method(self, *args, **kwargs)

    return scoped


def persist_playback(projector, item: WorkItem, binding, canonical: str, receipt: dict):
    if projector.fetch_audio is None:
        raise ProjectionBlocked('private playback requires ArtifactStore.fetch_audio')
    from database.conversations import decode_transcript_segments_verified

    # Reconstruct only this input's retained ranges from the stored legacy
    # transcript. Never put transcripts or unbounded survivor IDs in receipts.
    row = (
        projector.store.client.collection('users')
        .document(binding.owner_id)
        .collection('conversations')
        .document(canonical)
        .get()
        .to_dict()
        or {}
    )
    if not row or row.get('deleted'):
        raise ProjectionBlocked('playback target deleted')
    segments = decode_transcript_segments_verified(
        binding.owner_id,
        row.get('transcript_segments'),
        bool(row.get('transcript_segments_compressed')),
    )
    origin = row['started_at'].timestamp()
    capture_at = receipt.get('capture_at') or item.capture_at
    scope = receipt.get('speaker_scope') or f'sync:{item.segment_id}'
    survivors = []
    for segment in segments:
        if segment.get('speaker_id_scope') == scope:
            stamp = origin + segment['start']
            if scope.startswith('final:batch:') and not (
                capture_at <= stamp < (receipt.get('audio_end') or item.capture_at + item.duration_seconds)
            ):
                continue
            survivors.append(
                {
                    **segment,
                    'timestamp': stamp,
                    'start': stamp - capture_at,
                    'end': origin + segment['end'] - capture_at,
                }
            )
    if not survivors:
        return
    try:
        audio = projector.fetch_audio(item)
    except NotFound:  # Transcript is projected; close like a no-survivor input.
        return artifact_missing.record('playback')
    audio_end = receipt.get('audio_end') or item.capture_at + item.duration_seconds
    if capture_at != item.capture_at or audio_end != item.capture_at + item.duration_seconds:
        import io
        from pydub import AudioSegment

        # Match legacy retrieve_vad_segments slicing before full/partial
        # audio policy. Never copy a whole multipart capture to each row.
        decoded = AudioSegment.from_wav(io.BytesIO(audio))
        sliced = decoded[(capture_at - item.capture_at) * 1000 : (audio_end - item.capture_at) * 1000]
        output = io.BytesIO()
        sliced.export(output, format='wav')
        audio = output.getvalue()
    # Deliberately share the legacy audio persistence and partial-overlap
    # policy; its stable chunk timestamps make replay an overwrite.
    from utils.sync.merge_audio import store_intake_audio

    store_intake_audio(
        binding.owner_id,
        capture_at,
        audio,
        binding.data_protection_level,
        survivors,
        receipt['incoming_segment_count'],
        True,
        canonical,
    )
