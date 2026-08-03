"""Speaker assignment state and embedding matching for listen sessions."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, Dict, Optional, cast

import av
import numpy as np

from utils.audio import AudioRingBuffer
from utils.executors import storage_executor, sync_executor, run_blocking
from utils.other.storage import get_profile_audio_if_exists
from utils.speaker_sample import download_sample_audio
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.stt.speaker_embedding import SPEAKER_MATCH_THRESHOLD, compare_embeddings, extract_embedding_from_bytes
from utils.transcribe_decisions import USER_SELF_PERSON_ID, should_spawn_speaker_match
from utils.transcribe_store import user_db

logger = logging.getLogger(__name__)

MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS = 10.0


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as audio_file:
        return audio_file.read()


class SpeakerMatcher:
    def __init__(self, host: Any):
        self.host = host
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.person_embeddings: Dict[str, Dict[str, Any]] = {}
        self.speaker_to_person: Dict[int, tuple[str, str]] = {}
        self.segment_assignments: Dict[str, str] = {}
        self.tasks: set[asyncio.Task[Any]] = set()

    async def load_and_run(self) -> None:
        state = self.host.state
        if not state.speaker_id_enabled:
            state.speaker_id_done.set()
            return
        if self.host.has_speech_profile:
            try:
                embedding = await self.host.persistence.call(user_db.get_user_speaker_embedding, self.host.request.uid)
                if embedding:
                    self.person_embeddings[USER_SELF_PERSON_ID] = {
                        'embedding': np.array(embedding, dtype=np.float32).reshape(1, -1),
                        'name': 'User',
                    }
                else:
                    path = await run_blocking(storage_executor, get_profile_audio_if_exists, self.host.request.uid)
                    if path:
                        profile = await run_blocking(storage_executor, _read_file, path)
                        result = await run_blocking(
                            sync_executor, cast(Any, extract_embedding_from_bytes), profile, 'speech_profile.wav'
                        )
                        del profile
                        self.person_embeddings[USER_SELF_PERSON_ID] = {'embedding': result, 'name': 'User'}
                        await self.host.persistence.call(
                            user_db.set_user_speaker_embedding, self.host.request.uid, result.flatten().tolist()
                        )
            except Exception as error:
                logger.error('Speaker ID user embedding load failed type=%s', type(error).__name__)
        try:
            people = await self.host.persistence.call(user_db.get_people, self.host.request.uid)
            for person in people:
                if person.get('speech_samples'):
                    person = await maybe_migrate_person_samples(self.host.request.uid, person)
                stored = person.get('speaker_embedding')
                verified_samples = bool(person.get('speech_samples')) and (person.get('speech_samples_version', 1) >= 3)
                vector: Optional[Any] = None
                if verified_samples:
                    if stored:
                        vector = np.array(stored, dtype=np.float32).reshape(1, -1)
                    else:
                        vector = await self._recover_person_embedding(person)
                if vector is not None:
                    self.person_embeddings[person['id']] = {'embedding': vector, 'name': person['name']}
        except Exception as error:
            logger.error('Speaker ID embeddings load failed type=%s', type(error).__name__)
            state.speaker_id_done.set()
            return
        if not self.person_embeddings:
            state.speaker_id_done.set()
            return
        while True:
            try:
                segment = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if not state.active:
                    break
                continue
            speaker_id = segment['speaker_id']
            if should_spawn_speaker_match(
                speaker_already_mapped=speaker_id in self.speaker_to_person,
                duration=segment['duration'],
                min_audio_seconds=self.host.limits.speaker_id_min_audio,
            ):
                task = self.host.spawn(self.match(speaker_id, segment), name='speaker_match')
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
        state.speaker_id_done.set()

    async def _recover_person_embedding(self, person: Dict[str, Any]) -> Optional[Any]:
        """Rebuild a taught person's missing embedding from their stored samples.

        The teach path extracts the embedding inside a try/except that only logs, so a
        failed extraction leaves a person holding samples with no embedding, and nothing
        ever recomputes it. That person is then skipped here on every later session and
        can never be matched no matter how many times the user teaches them (#10434) —
        while the user's own profile self-heals through exactly this fallback above.

        Only reached for `speech_samples_version >= 3` samples, which already passed
        verify_and_transcribe_sample when they were stored, so this restores a lost
        embedding without reopening the quality gate that deliberately drops bad samples.
        """
        person_id = person.get('id')
        samples = person.get('speech_samples') or []
        if not samples:
            return None
        try:
            audio = await run_blocking(storage_executor, download_sample_audio, samples[0])
            if not audio:
                return None
            vector = await run_blocking(sync_executor, cast(Any, extract_embedding_from_bytes), audio, 'sample.wav')
            await self.host.persistence.call(
                user_db.set_person_speaker_embedding, self.host.request.uid, person_id, vector.flatten().tolist()
            )
            logger.info('Speaker ID recovered missing person embedding person=%s', person_id)
            return vector
        except Exception as error:
            logger.error(
                'Speaker ID person embedding recovery failed person=%s type=%s', person_id, type(error).__name__
            )
            return None

    async def match(self, speaker_id: int, segment: dict[str, Any]) -> None:
        try:
            ring_buffer: Optional[AudioRingBuffer] = self.host.state.audio_ring_buffer
            if ring_buffer is None or segment['duration'] < self.host.limits.speaker_id_min_audio:
                return
            time_range = ring_buffer.get_time_range()
            if time_range is None:
                return
            buffer_start, buffer_end = time_range
            segment_start = segment['abs_start']
            segment_end = segment['abs_end']
            if segment['duration'] <= MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS:
                extract_start, extract_end = segment_start, segment_end
            else:
                center = (segment_start + segment_end) / 2
                half_window = MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS / 2
                extract_start, extract_end = center - half_window, center + half_window
            extract_start = max(buffer_start, extract_start)
            extract_end = min(buffer_end, extract_end)
            if extract_end - extract_start < self.host.limits.speaker_id_min_audio:
                return
            pcm = ring_buffer.extract(extract_start, extract_end)
            if not pcm:
                return
            samples = np.frombuffer(pcm, dtype=np.int16)
            buffer = io.BytesIO()
            container = av.open(buffer, mode='w', format='wav')
            stream: Any = container.add_stream('pcm_s16le', rate=self.host.request.sample_rate)
            stream.layout = 'mono'
            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
            frame.rate = self.host.request.sample_rate
            for packet in stream.encode(frame):
                container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            container.close()
            query = await run_blocking(
                sync_executor, cast(Any, extract_embedding_from_bytes), buffer.getvalue(), 'query.wav'
            )
            best_id: Optional[str] = None
            best_name: Optional[str] = None
            best_distance = float('inf')
            for person_id, value in self.person_embeddings.items():
                distance = compare_embeddings(query, value['embedding'])
                if distance < best_distance:
                    best_id, best_name, best_distance = person_id, value['name'], distance
            if best_id and best_name and best_distance < SPEAKER_MATCH_THRESHOLD:
                self.speaker_to_person[speaker_id] = (best_id, best_name)
                self.segment_assignments[segment['id']] = best_id
                self.host.state.speaker_map_dirty = True
                self.host.emit_speaker_suggestion(speaker_id, best_id, best_name, segment['id'])
            else:
                logger.info('Speaker ID no match speaker=%s best_distance=%.3f', speaker_id, best_distance)
        except Exception as error:
            logger.error('Speaker ID match failed speaker=%s type=%s', speaker_id, type(error).__name__)

    async def drain(self, *, timeout: float, label: str) -> None:
        if self.tasks:
            await self.host.drain(list(self.tasks), timeout=timeout, label=label)

    def clear(self) -> None:
        self.person_embeddings.clear()
        self.speaker_to_person.clear()
        self.segment_assignments.clear()
