"""Helpers for tracking uploaded sync files whose VAD speech segments all transcribe to empty text."""

import os
import threading


def _is_safety_coverage_path(path: str, safety_coverage_paths: set[str] | None = None) -> bool:
    """Identify generated safety-coverage files by membership or parent directory name."""
    if safety_coverage_paths is not None and path in safety_coverage_paths:
        return True
    parent_dir = os.path.basename(os.path.dirname(os.path.normpath(path)))
    return parent_dir == 'safety-coverage'


def resolve_source_upload_filename(
    source_wav_path: str,
    raw_upload_names: list[str],
    safety_coverage_paths: set[str] | None = None,
) -> str:
    """Resolve a decoded WAV path back to its original uploaded filename."""
    base = os.path.basename(source_wav_path)
    stem = os.path.splitext(base)[0]
    candidate_bin = f'{stem}.bin'
    if candidate_bin in raw_upload_names:
        return candidate_bin
    if base in raw_upload_names:
        return base
    for name in raw_upload_names:
        if os.path.splitext(name)[0] == stem:
            return name
    if len(raw_upload_names) == 1 and not _is_safety_coverage_path(source_wav_path, safety_coverage_paths):
        return raw_upload_names[0]
    return candidate_bin if base.endswith('.wav') else base


def record_transcribed_segment_in_partial(
    response: dict,
    partial: dict,
    path: str,
    segment_id: str | None = None,
) -> None:
    """Record a transcribed segment in the retry partial-result checkpoint."""
    keys = response.setdefault('_transcribed_segments', set())
    keys.add(os.path.basename(path))
    if segment_id:
        keys.add(segment_id)
    partial['transcribed_segments'] = sorted(keys)


def restore_retry_silent_segment_paths(
    *,
    response: dict,
    partial_result: dict,
    durable_partial: dict | None,
    segmented_paths: set[str],
    already_processed: set[str],
    durable_processed_segment_ids: set[str],
    segment_ids_by_path: dict[str, str],
    silent_segment_paths: set[str],
) -> None:
    """Recover silent segment outcomes for segments already processed in an earlier attempt."""
    transcribed = set(partial_result.get('transcribed_segments') or []) | set(
        (durable_partial or {}).get('transcribed_segments') or []
    )
    if transcribed:
        response['_transcribed_segments'] = set(transcribed)
    has_legacy_memories = bool(
        partial_result.get('new_memories')
        or partial_result.get('updated_memories')
        or partial_result.get('fenced_conversation_ids')
    )
    for path in segmented_paths:
        seg_id = segment_ids_by_path.get(path)
        if path not in already_processed and not (seg_id and seg_id in durable_processed_segment_ids):
            continue
        if transcribed:
            is_silent = (
                os.path.basename(path) not in transcribed
                and path not in transcribed
                and (not seg_id or seg_id not in transcribed)
            )
        else:
            is_silent = not has_legacy_memories
        if is_silent:
            silent_segment_paths.add(path)


def compute_speech_without_text_files(
    *,
    raw_upload_names: list[str],
    segment_source_files: dict[str, str],
    silent_segment_paths: set[str],
    source_frame_maps: dict[str, dict] | None = None,
    safety_coverage_paths: set[str] | None = None,
) -> list[str]:
    """Return uploaded filenames whose every VAD speech segment transcribed to empty text."""
    if not silent_segment_paths or not segment_source_files:
        return []
    segments_by_source: dict[str, list[str]] = {}
    for seg_path, src_wav in segment_source_files.items():
        segments_by_source.setdefault(src_wav, []).append(seg_path)
    speech_without_text: set[str] = set()
    for src_wav, seg_paths in segments_by_source.items():
        if not seg_paths:
            continue
        if _is_safety_coverage_path(src_wav, safety_coverage_paths) or (
            (source_frame_maps or {}).get(src_wav) or {}
        ).get('coverage_trimmed'):
            continue
        if all(seg_path in silent_segment_paths for seg_path in seg_paths):
            speech_without_text.add(resolve_source_upload_filename(src_wav, raw_upload_names, safety_coverage_paths))
    return sorted(speech_without_text)


class SourceTrackingSegmentSet(set):
    """Forwards VAD segment additions to the shared set and maps each segment to its source WAV."""

    def __init__(
        self,
        backing: set,
        source_files: dict[str, str],
        source_path: str,
        lock: threading.RLock,
    ) -> None:
        super().__init__()
        self._backing = backing
        self._source_files = source_files
        self._source_path = source_path
        self._lock = lock

    def __contains__(self, item: object) -> bool:
        return item in self._backing

    def __len__(self) -> int:
        return len(self._backing)

    def __iter__(self):
        return iter(self._backing)

    def add(self, element: str) -> None:
        with self._lock:
            self._backing.add(element)
            self._source_files[element] = self._source_path

    def update(self, *s) -> None:
        with self._lock:
            for iterable in s:
                for element in iterable:
                    self._backing.add(element)
                    self._source_files[element] = self._source_path
