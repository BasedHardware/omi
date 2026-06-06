"""WebSocket streaming session with VAD, ASR, and diarization.

Each StreamSession manages one WebSocket connection's lifecycle:
- Receives PCM16 audio chunks
- Runs Silero VAD to detect speech/silence
- Buffers speech, transcribes with NeMo when silence detected or max window reached
- Assigns speaker labels via embedding-based cosine clustering
- Returns segments with {text, start, end, speaker, detected_language}
"""

import asyncio
import io
import logging
import os
import tempfile
import threading
import wave as _wave
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from langdetect import detect as langdetect_detect
from langdetect.lang_detect_exception import LangDetectException
from scipy.spatial.distance import cdist
from transcribe import transcribe_file, _model as _asr_model, INFERENCE_MODE as _INFERENCE_MODE

try:
    from pyannote.audio import Model as _PyannoteModel, Inference as _PyannoteInference
except ImportError:
    _PyannoteModel = None
    _PyannoteInference = None

logger = logging.getLogger(__name__)

SPEECH_THRESHOLD = float(os.getenv("PARAKEET_VAD_THRESHOLD", "0.3"))
MIN_SPEECH_DURATION_S = float(os.getenv("PARAKEET_MIN_SPEECH_S", "0.5"))
HANGOVER_S = float(os.getenv("PARAKEET_HANGOVER_S", "0.8"))
CHUNK_SECONDS = float(os.getenv("PARAKEET_CHUNK_S", "2.0"))
LEFT_CONTEXT_SECONDS = float(os.getenv("PARAKEET_LEFT_CONTEXT_S", "10.0"))
SPEAKER_MATCH_THRESHOLD = float(os.getenv("PARAKEET_SPEAKER_THRESHOLD", "0.45"))
SPEAKER_EMBEDDING_URL = os.getenv("HOSTED_SPEAKER_EMBEDDING_API_URL", "")
MIN_EMBEDDING_AUDIO_S = 0.5

_embedding_model = None
_embedding_lock = threading.Lock()


def _get_builtin_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model
        try:
            if _PyannoteModel is None or _PyannoteInference is None:
                logger.warning("pyannote.audio not installed, built-in embedding unavailable")
                return None
            model = _PyannoteModel.from_pretrained(
                "pyannote/wespeaker-voxceleb-resnet34-LM", token=os.getenv("HUGGINGFACE_TOKEN")
            )
            inference = _PyannoteInference(model, window="whole")
            if _torch is not None:
                device = _torch.device("cuda" if _torch.cuda.is_available() else "cpu")
                inference.to(device)
            _embedding_model = inference
            logger.info("Built-in speaker embedding model loaded (wespeaker-voxceleb-resnet34-LM)")
            return _embedding_model
        except Exception as e:
            logger.warning(f"Could not load built-in embedding model: {e}")
            return None


_vad_model = None
_vad_lock = threading.Lock()
_asr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="parakeet_asr")

try:
    import torch
    import torchaudio

    _torch = torch
except ImportError:
    _torch = None
    torchaudio = None


def _get_vad_model():
    global _vad_model
    if _vad_model is not None:
        return _vad_model
    with _vad_lock:
        if _vad_model is not None:
            return _vad_model
        if _torch is None:
            logger.warning("torch not available, VAD disabled")
            return None
        try:
            model, _ = _torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)
            _vad_model = model
            logger.info("Silero VAD model loaded")
            return _vad_model
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}")
            return None


class StreamSession:
    """RNNT chunked streaming with left context and VAD-based endpointing.

    Audio flows continuously through 2s chunks with 10s left context.
    The full context window (left + current chunk) is transcribed each tick,
    but only the new text from the current chunk is emitted. VAD detects
    speech boundaries for endpointing (when to finalize and emit segments).
    """

    def __init__(self, sample_rate: int = 16000):
        self._sr = sample_rate
        self._bytes_per_sample = 2
        self._vad_chunk_samples = 512
        self._vad_chunk_bytes = self._vad_chunk_samples * self._bytes_per_sample

        self._pcm_buf = bytearray()
        self._audio_buf = bytearray()
        self._stream_offset_s = 0.0
        self._is_speaking = False
        self._speech_start_s = None
        self._silence_count = 0
        self._hangover_chunks = int(HANGOVER_S * self._sr / self._vad_chunk_samples)
        self._chunk_bytes = int(CHUNK_SECONDS * self._sr * self._bytes_per_sample)
        self._left_context_bytes = int(LEFT_CONTEXT_SECONDS * self._sr * self._bytes_per_sample)
        self._pending_audio = bytearray()
        self._prev_text = ""
        self._last_chunk_offset = 0

        self._spk_centroids = []
        self._spk_counts = []
        self._last_speaker = 0

        self._vad = _get_vad_model()

    async def feed(self, data: bytes):
        self._pcm_buf.extend(data)
        segments = []

        while len(self._pcm_buf) >= self._vad_chunk_bytes:
            vad_chunk = bytes(self._pcm_buf[: self._vad_chunk_bytes])
            del self._pcm_buf[: self._vad_chunk_bytes]

            is_speech = self._run_vad(vad_chunk)
            chunk_dur = self._vad_chunk_samples / self._sr

            if is_speech:
                self._silence_count = 0
                if not self._is_speaking:
                    self._is_speaking = True
                    self._speech_start_s = self._stream_offset_s
                    self._prev_text = ""
                    self._last_chunk_offset = 0
                self._pending_audio.extend(vad_chunk)
            else:
                if self._is_speaking:
                    self._silence_count += 1
                    self._pending_audio.extend(vad_chunk)

                    if self._silence_count >= self._hangover_chunks:
                        speech_dur = len(self._pending_audio) / (self._sr * self._bytes_per_sample)
                        if speech_dur >= MIN_SPEECH_DURATION_S:
                            result = await self._transcribe_utterance()
                            segments.extend(result)
                        self._pending_audio.clear()
                        self._is_speaking = False
                        self._speech_start_s = None
                        self._prev_text = ""
                        self._last_chunk_offset = 0

            pending_since_last = len(self._pending_audio) - self._last_chunk_offset
            if self._is_speaking and pending_since_last >= self._chunk_bytes:
                result = await self._transcribe_chunk()
                segments.extend(result)
                self._last_chunk_offset = len(self._pending_audio)

            self._stream_offset_s += chunk_dur
            self._audio_buf.extend(vad_chunk)
            if len(self._audio_buf) > self._left_context_bytes * 2:
                excess = len(self._audio_buf) - self._left_context_bytes
                del self._audio_buf[:excess]

        return segments

    async def flush(self):
        if not self._pending_audio or self._speech_start_s is None:
            return []
        speech_dur = len(self._pending_audio) / (self._sr * self._bytes_per_sample)
        if speech_dur < MIN_SPEECH_DURATION_S:
            return []
        return await self._transcribe_utterance()

    def cleanup(self):
        self._pcm_buf.clear()
        self._audio_buf.clear()
        self._pending_audio.clear()
        self._spk_centroids.clear()
        self._spk_counts.clear()

    def _run_vad(self, chunk: bytes) -> bool:
        if self._vad is None or _torch is None:
            return True
        try:
            audio = _torch.frombuffer(chunk, dtype=_torch.int16).float() / 32768.0
            prob = self._vad(audio, self._sr).item()
            return prob >= SPEECH_THRESHOLD
        except Exception:
            return True

    async def _transcribe_chunk(self):
        left_ctx = bytes(self._audio_buf[-self._left_context_bytes :]) if len(self._audio_buf) > 0 else b''
        full_audio = left_ctx + bytes(self._pending_audio)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(_asr_executor, self._transcribe_pcm, full_audio)

        new_text = result.get("text", "")
        if self._prev_text and new_text.startswith(self._prev_text):
            new_text = new_text[len(self._prev_text) :].strip()
        elif self._prev_text:
            prev_words = self._prev_text.split()
            new_words = new_text.split()
            overlap = 0
            for i in range(min(len(prev_words), len(new_words))):
                if prev_words[-(i + 1) :] == new_words[: i + 1]:
                    overlap = i + 1
            new_text = " ".join(new_words[overlap:]) if overlap > 0 else new_text

        self._prev_text = result.get("text", "")

        if not new_text.strip():
            return []

        chunk_start = self._speech_start_s or self._stream_offset_s
        chunk_dur = len(self._pending_audio) / (self._sr * self._bytes_per_sample)
        return self._build_segments(new_text, chunk_start, chunk_dur, bytes(self._pending_audio))

    async def _transcribe_utterance(self):
        speech_pcm = bytes(self._pending_audio)
        speech_start = self._speech_start_s or self._stream_offset_s

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(_asr_executor, self._transcribe_pcm, speech_pcm)

        text = result.get("text", "")
        raw_segments = result.get("segments", [])

        if not raw_segments and text:
            dur = len(speech_pcm) / (self._sr * self._bytes_per_sample)
            raw_segments = [{"text": text, "start": 0.0, "end": dur}]

        detected_lang = "en"
        if text and len(text.strip()) >= 10:
            try:
                detected_lang = langdetect_detect(text)
            except LangDetectException:
                pass

        output = []
        for seg in raw_segments:
            seg_text = (seg.get("text") or "").strip()
            if not seg_text:
                continue

            rel_start = float(seg.get("start", 0.0))
            rel_end = float(seg.get("end", rel_start))
            abs_start = speech_start + rel_start
            abs_end = speech_start + rel_end

            loop2 = asyncio.get_running_loop()
            speaker = await loop2.run_in_executor(None, self._assign_speaker, speech_pcm, rel_start, rel_end)

            output.append(
                {
                    "text": seg_text,
                    "start": round(abs_start, 2),
                    "end": round(abs_end, 2),
                    "speaker": speaker,
                    "is_user": False,
                    "person_id": None,
                    "detected_language": detected_lang,
                }
            )

        return output

    def _build_segments(self, text, start_s, dur_s, pcm):
        if not text.strip():
            return []
        detected_lang = "en"
        if len(text.strip()) >= 10:
            try:
                detected_lang = langdetect_detect(text)
            except LangDetectException:
                pass
        speaker = self._assign_speaker(pcm, 0, dur_s)
        return [
            {
                "text": text.strip(),
                "start": round(start_s, 2),
                "end": round(start_s + dur_s, 2),
                "speaker": speaker,
                "is_user": False,
                "person_id": None,
                "detected_language": detected_lang,
            }
        ]

    def _transcribe_pcm(self, pcm_bytes: bytes):
        if _INFERENCE_MODE == "nim" or _asr_model is None:
            return self._transcribe_pcm_via_file(pcm_bytes)

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        hyps = _asr_model.transcribe([audio], timestamps=True)
        hyp = hyps[0]
        text = getattr(hyp, "text", None) or ""

        segments = []
        timestamp = getattr(hyp, "timestamp", None) or {}
        for s in timestamp.get("segment", []) or []:
            segments.append(
                {
                    "text": s.get("segment", ""),
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                }
            )
        if not segments and text:
            dur = len(pcm_bytes) / (self._sr * self._bytes_per_sample)
            segments = [{"text": text, "start": 0.0, "end": dur}]

        del audio
        return {"text": text, "segments": segments}

    def _transcribe_pcm_via_file(self, pcm_bytes: bytes):
        wav_bytes = self._pcm_to_wav(pcm_bytes)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wav_bytes)
        tmp.close()
        del wav_bytes
        try:
            return transcribe_file(tmp.name)
        finally:
            os.unlink(tmp.name)

    def _assign_speaker(self, pcm: bytes, start: float, end: float) -> str:
        if end - start < 0.6:
            return f"SPEAKER_{self._last_speaker}"

        try:
            start_byte = int(start * self._sr * self._bytes_per_sample)
            end_byte = int(end * self._sr * self._bytes_per_sample)
            seg_pcm = pcm[start_byte:end_byte]

            if len(seg_pcm) < int(0.6 * self._sr * self._bytes_per_sample):
                return f"SPEAKER_{self._last_speaker}"

            seg_wav = self._pcm_to_wav(seg_pcm)
            emb = self._get_embedding(seg_wav)
            if emb is None:
                return f"SPEAKER_{self._last_speaker}"

            best_i, best_dist = -1, 1e9
            for i, c in enumerate(self._spk_centroids):
                d = float(cdist(emb, c, metric="cosine")[0, 0])
                if d < best_dist:
                    best_i, best_dist = i, d

            if best_i >= 0 and best_dist < SPEAKER_MATCH_THRESHOLD:
                n = self._spk_counts[best_i]
                self._spk_centroids[best_i] = (self._spk_centroids[best_i] * n + emb) / (n + 1)
                self._spk_counts[best_i] = n + 1
                self._last_speaker = best_i
                return f"SPEAKER_{best_i}"

            self._spk_centroids.append(emb)
            self._spk_counts.append(1)
            self._last_speaker = len(self._spk_centroids) - 1
            return f"SPEAKER_{self._last_speaker}"

        except Exception as e:
            logger.warning(f"Speaker assignment failed: {e}")
            return f"SPEAKER_{self._last_speaker}"

    def _get_embedding(self, wav_bytes: bytes):
        model = _get_builtin_embedding_model()
        if model is not None:
            return self._get_embedding_builtin(wav_bytes, model)
        if SPEAKER_EMBEDDING_URL:
            return self._get_embedding_http(wav_bytes)
        return None

    def _get_embedding_builtin(self, wav_bytes: bytes, model):
        try:
            buf = io.BytesIO(wav_bytes)
            waveform, sample_rate = torchaudio.load(buf)
            dur = waveform.shape[1] / sample_rate
            if dur < MIN_EMBEDDING_AUDIO_S:
                return None
            emb = model({"waveform": waveform, "sample_rate": sample_rate})
            emb = np.array(emb, dtype=np.float32)
            if emb.ndim == 1:
                emb = emb.reshape(1, -1)
            return emb
        except Exception as e:
            logger.warning(f"Built-in embedding failed: {e}")
            return None

    def _get_embedding_http(self, wav_bytes: bytes):
        try:
            with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)) as client:
                resp = client.post(
                    f"{SPEAKER_EMBEDDING_URL}/v2/embedding",
                    files={"file": ("segment.wav", wav_bytes, "audio/wav")},
                )
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, list):
                emb = np.array(result, dtype=np.float32)
            else:
                emb = np.array(result["embedding"], dtype=np.float32)
            if emb.ndim == 1:
                emb = emb.reshape(1, -1)
            return emb
        except Exception as e:
            logger.warning(f"HTTP embedding failed: {e}")
            return None

    def _pcm_to_wav(self, pcm: bytes) -> bytes:
        buf = io.BytesIO()
        with _wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(self._bytes_per_sample)
            wf.setframerate(self._sr)
            wf.writeframes(pcm)
        return buf.getvalue()
