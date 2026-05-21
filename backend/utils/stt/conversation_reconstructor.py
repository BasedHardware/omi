from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from models.transcript_segment import (
    ProviderTranscriptResult,
    ProviderTranscriptUtterance,
    ProviderTranscriptWord,
    TranscriptSegment,
)


@dataclass
class _SegmentCandidate:
    text: str
    start: float
    end: float
    provider_cluster_id: Optional[str]
    speaker_label: Optional[str]


class ConversationReconstructor:
    def __init__(self, max_same_cluster_gap_seconds: float = 30.0):
        self.max_same_cluster_gap_seconds = max_same_cluster_gap_seconds

    def reconstruct(
        self,
        result: ProviderTranscriptResult,
        skip_n_seconds: int = 0,
        user_provider_cluster_id: Optional[str] = None,
    ) -> List[TranscriptSegment]:
        user_cluster_id = user_provider_cluster_id or self._retrieve_user_cluster_id(result, skip_n_seconds)
        candidates = self._build_candidates(result, skip_n_seconds)
        candidates = [candidate for candidate in candidates if candidate.start >= skip_n_seconds and candidate.text]
        candidates = self._sort_and_dedupe_candidates(candidates)
        candidates = self._merge_adjacent_candidates(candidates)

        if not candidates:
            return []

        starts_at = candidates[0].start
        segments = []
        for candidate in candidates:
            is_user = bool(user_cluster_id and candidate.provider_cluster_id == user_cluster_id)
            speaker_label = self._legacy_speaker_label(candidate.speaker_label)
            identity_state = self._identity_state(is_user, candidate.provider_cluster_id, speaker_label)
            segments.append(
                TranscriptSegment(
                    text=candidate.text.strip().capitalize(),
                    speaker=speaker_label,
                    is_user=is_user,
                    person_id=None,
                    start=round(candidate.start - starts_at, 2),
                    end=round(candidate.end - starts_at, 2),
                    stt_provider=result.provider,
                    stt_model=result.model,
                    provider_cluster_id=candidate.provider_cluster_id,
                    provider_speaker_label=candidate.speaker_label,
                    speaker_identity_state=identity_state,
                )
            )
        return segments

    def _build_candidates(self, result: ProviderTranscriptResult, skip_n_seconds: int) -> List[_SegmentCandidate]:
        candidates = self._utterance_candidates(result.utterances)
        if not result.words:
            return candidates

        candidate_words = [word for word in result.words if word.start >= skip_n_seconds]
        if not candidates:
            return self._word_candidates(candidate_words)

        covered_intervals = [(candidate.start, candidate.end) for candidate in candidates]
        uncovered_words = [word for word in candidate_words if not self._word_is_covered(word, covered_intervals)]
        return candidates + self._word_candidates(uncovered_words)

    def _utterance_candidates(self, utterances: Sequence[ProviderTranscriptUtterance]) -> List[_SegmentCandidate]:
        candidates = []
        for utterance in utterances:
            text = utterance.text.strip()
            if not text and utterance.words:
                text = ' '.join(word.text.strip() for word in utterance.words if word.text.strip())
            if not text:
                continue
            provider_cluster_id = utterance.provider_cluster_id
            speaker_label = utterance.speaker_label
            if utterance.words and (not provider_cluster_id or not speaker_label):
                provider_cluster_id, speaker_label = self._dominant_speaker(utterance.words)
            candidates.append(
                _SegmentCandidate(
                    text=text,
                    start=utterance.start,
                    end=utterance.end,
                    provider_cluster_id=provider_cluster_id,
                    speaker_label=speaker_label,
                )
            )
        return candidates

    def _word_candidates(self, words: Sequence[ProviderTranscriptWord]) -> List[_SegmentCandidate]:
        candidates = []
        normalized_words = self._interpolate_missing_word_speakers(
            sorted(words, key=lambda item: (item.start, item.end))
        )
        for word in normalized_words:
            text = word.text.strip()
            if not text:
                continue
            if candidates and self._should_merge_word(candidates[-1], word):
                candidates[-1].text = f'{candidates[-1].text} {text}'
                candidates[-1].end = word.end
                continue
            candidates.append(
                _SegmentCandidate(
                    text=text,
                    start=word.start,
                    end=word.end,
                    provider_cluster_id=word.provider_cluster_id,
                    speaker_label=word.speaker_label,
                )
            )
        return candidates

    def _interpolate_missing_word_speakers(
        self, words: Sequence[ProviderTranscriptWord]
    ) -> List[ProviderTranscriptWord]:
        normalized_words = [word.model_copy() for word in words]
        for index, word in enumerate(normalized_words):
            if word.provider_cluster_id or word.speaker_label:
                continue

            previous_word = normalized_words[index - 1] if index > 0 else None
            next_word = normalized_words[index + 1] if index < len(normalized_words) - 1 else None
            previous_has_speaker = previous_word and (previous_word.provider_cluster_id or previous_word.speaker_label)
            next_has_speaker = next_word and (next_word.provider_cluster_id or next_word.speaker_label)
            if previous_has_speaker and next_has_speaker:
                if previous_word.provider_cluster_id == next_word.provider_cluster_id:
                    word.provider_cluster_id = previous_word.provider_cluster_id
                    word.speaker_label = previous_word.speaker_label
                else:
                    secs_from_previous = word.start - previous_word.end
                    secs_to_next = next_word.start - word.end
                    source = previous_word if secs_from_previous < secs_to_next else next_word
                    word.provider_cluster_id = source.provider_cluster_id
                    word.speaker_label = source.speaker_label
            elif previous_has_speaker:
                word.provider_cluster_id = previous_word.provider_cluster_id
                word.speaker_label = previous_word.speaker_label
            elif next_has_speaker:
                word.provider_cluster_id = next_word.provider_cluster_id
                word.speaker_label = next_word.speaker_label
        return normalized_words

    def _sort_and_dedupe_candidates(self, candidates: Sequence[_SegmentCandidate]) -> List[_SegmentCandidate]:
        ordered = sorted(candidates, key=lambda item: (item.start, item.end))
        deduped = []
        for candidate in ordered:
            if not deduped:
                deduped.append(candidate)
                continue

            previous = deduped[-1]
            if self._is_duplicate_overlap(previous, candidate):
                if len(candidate.text) > len(previous.text):
                    candidate.start = min(previous.start, candidate.start)
                    candidate.end = max(previous.end, candidate.end)
                    deduped[-1] = candidate
                continue
            deduped.append(candidate)
        return deduped

    def _merge_adjacent_candidates(self, candidates: Sequence[_SegmentCandidate]) -> List[_SegmentCandidate]:
        merged = []
        for candidate in candidates:
            if merged and self._should_merge_candidate(merged[-1], candidate):
                merged[-1].text = f'{merged[-1].text} {candidate.text}'
                merged[-1].end = candidate.end
                continue
            merged.append(candidate)
        return merged

    def _retrieve_user_cluster_id(self, result: ProviderTranscriptResult, skip_n_seconds: int) -> Optional[str]:
        if not skip_n_seconds:
            return None

        speaker_counts = {}
        speaker_sources: Iterable[Tuple[float, Optional[str]]] = (
            [(word.start, word.provider_cluster_id) for word in result.words]
            if result.words
            else [(utterance.start, utterance.provider_cluster_id) for utterance in result.utterances]
        )
        for start, provider_cluster_id in sorted(speaker_sources, key=lambda item: item[0]):
            if start >= skip_n_seconds:
                break
            if not provider_cluster_id:
                continue
            speaker_counts[provider_cluster_id] = speaker_counts.get(provider_cluster_id, 0) + 1
        return max(speaker_counts, key=speaker_counts.get) if speaker_counts else None

    def _dominant_speaker(self, words: Sequence[ProviderTranscriptWord]) -> Tuple[Optional[str], Optional[str]]:
        speaker_counts = {}
        labels_by_cluster = {}
        for word in words:
            if not word.provider_cluster_id:
                continue
            speaker_counts[word.provider_cluster_id] = speaker_counts.get(word.provider_cluster_id, 0) + 1
            if word.speaker_label:
                labels_by_cluster[word.provider_cluster_id] = word.speaker_label

        if not speaker_counts:
            return None, None

        cluster_id = max(speaker_counts, key=speaker_counts.get)
        return cluster_id, labels_by_cluster.get(cluster_id)

    def _word_is_covered(self, word: ProviderTranscriptWord, intervals: Sequence[Tuple[float, float]]) -> bool:
        return any(start <= word.start and word.end <= end for start, end in intervals)

    def _should_merge_word(self, previous: _SegmentCandidate, word: ProviderTranscriptWord) -> bool:
        return (
            previous.provider_cluster_id == word.provider_cluster_id
            and word.start - previous.end < self.max_same_cluster_gap_seconds
        )

    def _should_merge_candidate(self, previous: _SegmentCandidate, candidate: _SegmentCandidate) -> bool:
        return (
            previous.provider_cluster_id == candidate.provider_cluster_id
            and candidate.start - previous.end < self.max_same_cluster_gap_seconds
        )

    def _is_duplicate_overlap(self, previous: _SegmentCandidate, candidate: _SegmentCandidate) -> bool:
        if candidate.start >= previous.end:
            return False

        previous_text = self._normalize_text(previous.text)
        candidate_text = self._normalize_text(candidate.text)
        return (
            bool(previous_text and candidate_text)
            and previous.provider_cluster_id == candidate.provider_cluster_id
            and (previous_text == candidate_text or previous_text in candidate_text or candidate_text in previous_text)
        )

    def _legacy_speaker_label(self, speaker_label: Optional[str]) -> Optional[str]:
        if isinstance(speaker_label, str) and speaker_label.startswith('SPEAKER_'):
            return speaker_label
        return None

    def _identity_state(self, is_user: bool, provider_cluster_id: Optional[str], speaker_label: Optional[str]) -> str:
        if is_user:
            return 'user'
        if speaker_label:
            return 'unassigned'
        return 'unknown'

    def _normalize_text(self, text: str) -> str:
        return ' '.join(text.lower().split())


def reconstruct_conversation(
    result: ProviderTranscriptResult,
    skip_n_seconds: int = 0,
    user_provider_cluster_id: Optional[str] = None,
) -> List[TranscriptSegment]:
    return ConversationReconstructor().reconstruct(result, skip_n_seconds, user_provider_cluster_id)
