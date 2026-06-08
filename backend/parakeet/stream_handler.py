"""WebSocket streaming session with VAD, ASR, and diarization.

Each StreamSession manages one WebSocket connection's lifecycle:
- Receives PCM16 audio chunks
- Runs Silero VAD to detect speech/silence
- Buffers speech, transcribes with NeMo when silence detected or max window reached
- Assigns speaker labels via embedding-based cosine clustering
- Returns segments with {text, start, end, speaker, detected_language}
"""

import asyncio
import copy
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
from transcribe import transcribe_file, _stream_model as _asr_model, INFERENCE_MODE as _INFERENCE_MODE

try:
    from pyannote.audio import Model as _PyannoteModel, Inference as _PyannoteInference
except ImportError:
    _PyannoteModel = None
    _PyannoteInference = None

logger = logging.getLogger(__name__)

SPEECH_THRESHOLD = float(os.getenv("PARAKEET_VAD_THRESHOLD", "0.5"))
MIN_SPEECH_DURATION_S = float(os.getenv("PARAKEET_MIN_SPEECH_S", "0.5"))
MAX_SPEECH_DURATION_S = float(os.getenv("PARAKEET_MAX_SPEECH_S", "30.0"))
AGC_TARGET_PEAK = float(os.getenv("PARAKEET_AGC_TARGET", "0.8"))
HANGOVER_S = float(os.getenv("PARAKEET_HANGOVER_S", "0.8"))
CHUNK_SECONDS = float(os.getenv("PARAKEET_CHUNK_S", "2.0"))
LEFT_CONTEXT_SECONDS = float(os.getenv("PARAKEET_LEFT_CONTEXT_S", "10.0"))
RIGHT_CONTEXT_SECONDS = float(os.getenv("PARAKEET_RIGHT_CONTEXT_S", "2.0"))
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
_streaming_import_error_logged = False
_rnnt_model_initialized = False

try:
    import torch

    _torch = torch
except ImportError:
    _torch = None

try:
    import torchaudio
except ImportError:
    torchaudio = None


def _make_divisible_by(num, factor: int) -> int:
    return (num // factor) * factor


def _cfg_get(cfg, path: str, default=None):
    cur = cfg
    for part in path.split("."):
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(part, default)
        else:
            cur = getattr(cur, part, default)
    return cur


def _cfg_set(cfg, path: str, value):
    cur = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur[part] if isinstance(cur, dict) else getattr(cur, part)
    if isinstance(cur, dict):
        cur[parts[-1]] = value
    else:
        setattr(cur, parts[-1], value)


def warmup_rnnt_decoder(sample_rate: int = 16000):
    """Run a dummy chunk through the RNNT decoder to pre-compile CUDA kernels.

    Call once at service startup to eliminate 15-20s cold-start latency
    on the first real WebSocket connection.
    """
    if _asr_model is None or _INFERENCE_MODE == "nim":
        logger.info("RNNT warmup skipped (no stream model or NIM mode)")
        return

    if not hasattr(_asr_model, 'decoding') or not hasattr(
        getattr(_asr_model.decoding, 'decoding', None), 'decoding_computer'
    ):
        logger.info("RNNT warmup skipped (model does not support RNNT streaming)")
        return

    logger.info("RNNT warmup: running dummy chunk to pre-compile CUDA kernels...")
    try:
        decoder = _NemoRNNTStreamingDecoder(
            model=_asr_model,
            sample_rate=sample_rate,
            chunk_seconds=CHUNK_SECONDS,
            left_context_seconds=LEFT_CONTEXT_SECONDS,
            right_context_seconds=RIGHT_CONTEXT_SECONDS,
        )
        dummy_pcm = b'\x00' * int(sample_rate * 2 * 3)
        decoder.decode_pcm(dummy_pcm, is_last_chunk=True)
        logger.info("RNNT warmup complete")
    except Exception as e:
        logger.warning(f"RNNT warmup failed (non-fatal): {e}")


class _NemoRNNTStreamingDecoder:
    """NeMo RNNT chunked decoder for one live stream.

    This mirrors NeMo's `speech_to_text_streaming_infer_rnnt.py` pattern:
    `StreamingBatchedAudioBuffer` manages left/chunk/right audio context, while
    `prev_batched_state` is fed back into the RNNT decoding computer.
    """

    def __init__(
        self,
        model,
        sample_rate: int,
        chunk_seconds: float,
        left_context_seconds: float,
        right_context_seconds: float,
    ):
        self._model = model
        self._sr = sample_rate
        self._chunk_seconds = chunk_seconds
        self._left_context_seconds = left_context_seconds
        self._right_context_seconds = right_context_seconds
        self._initialized = False
        self._started = False
        self._state = None
        self._current_batched_hyps = None
        self._text = ""

    def _ensure_initialized(self):
        global _streaming_import_error_logged, _rnnt_model_initialized

        if self._initialized:
            return

        if _torch is None:
            raise RuntimeError("torch is required for NeMo RNNT streaming")

        try:
            from omegaconf import open_dict

            from nemo.collections.asr.parts.submodules.rnnt_decoding import RNNTDecodingConfig
            from nemo.collections.asr.parts.utils.rnnt_utils import batched_hyps_to_hypotheses
            from nemo.collections.asr.parts.utils.streaming_utils import ContextSize, StreamingBatchedAudioBuffer
        except Exception as e:
            if not _streaming_import_error_logged:
                logger.warning(f"NeMo RNNT streaming utilities unavailable, using batch fallback: {e}")
                _streaming_import_error_logged = True
            raise

        self._batched_hyps_to_hypotheses = batched_hyps_to_hypotheses
        self._ContextSize = ContextSize
        self._StreamingBatchedAudioBuffer = StreamingBatchedAudioBuffer

        model = self._model

        if not _rnnt_model_initialized:
            model.freeze() if hasattr(model, "freeze") else None
            model.eval()

            decoding_cfg = copy.deepcopy(_cfg_get(getattr(model, "cfg", None), "decoding", None))
            if decoding_cfg is None:
                decoding_cfg = RNNTDecodingConfig()

            with open_dict(decoding_cfg):
                _cfg_set(decoding_cfg, "strategy", "greedy_batch")
                _cfg_set(decoding_cfg, "greedy.loop_labels", True)
                _cfg_set(decoding_cfg, "greedy.preserve_alignments", False)
                _cfg_set(decoding_cfg, "fused_batch_size", -1)
                _cfg_set(decoding_cfg, "beam.return_best_hypothesis", True)
                try:
                    _cfg_set(decoding_cfg, "greedy.use_cuda_graph_decoder", False)
                except Exception:
                    pass

            if hasattr(model, "change_decoding_strategy"):
                model.change_decoding_strategy(decoding_cfg)

            if hasattr(model.preprocessor, "featurizer"):
                model.preprocessor.featurizer.dither = 0.0
                model.preprocessor.featurizer.pad_to = 0

            _rnnt_model_initialized = True

        model_cfg = getattr(model, "_cfg", getattr(model, "cfg", None))
        model_sr = int(_cfg_get(model_cfg, "preprocessor.sample_rate", self._sr))
        if model_sr != self._sr:
            raise RuntimeError(f"Parakeet streaming expects {model_sr} Hz audio, got {self._sr} Hz")

        feature_stride_sec = float(_cfg_get(model_cfg, "preprocessor.window_stride", 0.01))
        features_per_sec = 1.0 / feature_stride_sec
        encoder_subsampling_factor = int(getattr(model.encoder, "subsampling_factor", 1))
        features_frame2audio_samples = _make_divisible_by(
            int(self._sr * feature_stride_sec), factor=encoder_subsampling_factor
        )
        self._encoder_frame2audio_samples = features_frame2audio_samples * encoder_subsampling_factor

        context_encoder_frames = ContextSize(
            left=int(self._left_context_seconds * features_per_sec / encoder_subsampling_factor),
            chunk=int(self._chunk_seconds * features_per_sec / encoder_subsampling_factor),
            right=int(self._right_context_seconds * features_per_sec / encoder_subsampling_factor),
        )
        self._context_samples = ContextSize(
            left=context_encoder_frames.left * encoder_subsampling_factor * features_frame2audio_samples,
            chunk=context_encoder_frames.chunk * encoder_subsampling_factor * features_frame2audio_samples,
            right=context_encoder_frames.right * encoder_subsampling_factor * features_frame2audio_samples,
        )

        if _cfg_get(model_cfg, "encoder.att_context_style") == "chunked_limited_with_rc" and hasattr(
            model.encoder, "set_default_att_context_size"
        ):
            model.encoder.set_default_att_context_size(
                att_context_size=[
                    context_encoder_frames.left,
                    context_encoder_frames.chunk,
                    context_encoder_frames.right,
                ]
            )

        self._device = getattr(model, "device", None)
        if self._device is None:
            self._device = next(model.parameters()).device
        self._buffer = StreamingBatchedAudioBuffer(
            batch_size=1,
            context_samples=self._context_samples,
            dtype=_torch.float32,
            device=self._device,
        )
        self._decoding_computer = model.decoding.decoding.decoding_computer
        self._initialized = True

        logger.info(
            "Parakeet RNNT streaming contexts: left=%.2fs chunk=%.2fs right=%.2fs",
            self._context_samples.left / self._sr,
            self._context_samples.chunk / self._sr,
            self._context_samples.right / self._sr,
        )

    def next_input_bytes(self, bytes_per_sample: int) -> int:
        self._ensure_initialized()
        if not self._started:
            samples = self._context_samples.chunk + self._context_samples.right
        else:
            samples = self._context_samples.chunk
        return samples * bytes_per_sample

    def decode_pcm(self, pcm_bytes: bytes, is_last_chunk: bool = False) -> str:
        self._ensure_initialized()
        if not pcm_bytes:
            return self._text

        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        audio_batch = _torch.from_numpy(audio_np).unsqueeze(0).to(device=self._device)
        audio_lengths = _torch.tensor([audio_np.shape[0]], dtype=_torch.long, device=self._device)
        is_last_chunk_batch = _torch.tensor([is_last_chunk], dtype=_torch.bool, device=self._device)

        with _torch.no_grad(), _torch.inference_mode():
            self._buffer.add_audio_batch_(
                audio_batch,
                audio_lengths=audio_lengths,
                is_last_chunk=is_last_chunk,
                is_last_chunk_batch=is_last_chunk_batch,
            )

            encoder_output, encoder_output_len = self._model(
                input_signal=self._buffer.samples,
                input_signal_length=self._buffer.context_size_batch.total(),
            )
            encoder_output = encoder_output.transpose(1, 2)
            encoder_context = self._buffer.context_size.subsample(factor=self._encoder_frame2audio_samples)
            encoder_context_batch = self._buffer.context_size_batch.subsample(factor=self._encoder_frame2audio_samples)
            encoder_output = encoder_output[:, encoder_context.left :]
            out_len = _torch.where(
                is_last_chunk_batch,
                encoder_output_len - encoder_context_batch.left,
                encoder_context_batch.chunk,
            )

            decode_result = self._decoding_computer(
                x=encoder_output,
                out_len=out_len,
                prev_batched_state=self._state,
                multi_biasing_ids=None,
            )
            if isinstance(decode_result, tuple):
                chunk_batched_hyps = decode_result[0]
                self._state = decode_result[1]
            else:
                chunk_batched_hyps = decode_result
                self._state = None

            if self._current_batched_hyps is None:
                self._current_batched_hyps = chunk_batched_hyps
            else:
                self._current_batched_hyps.merge_(chunk_batched_hyps)

            hyp = self._batched_hyps_to_hypotheses(self._current_batched_hyps, batch_size=1)[0]
            self._text = self._model.tokenizer.ids_to_text(hyp.y_sequence.tolist())
            self._started = True
            return self._text


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
    """RNNT chunked streaming with context and VAD-based endpointing.

    Audio flows continuously through left/chunk/right context windows. RNNT
    decoder state is preserved across chunks; VAD only decides when to emit
    the latest decoded text delta as a segment.
    """

    def __init__(self, sample_rate: int = 16000, vad_threshold: float = None, hangover_s: float = None):
        self._sr = sample_rate
        self._bytes_per_sample = 2
        self._vad_chunk_samples = 512
        self._vad_chunk_bytes = self._vad_chunk_samples * self._bytes_per_sample
        self._speech_threshold = vad_threshold if vad_threshold is not None else SPEECH_THRESHOLD
        self._hangover_s = hangover_s if hangover_s is not None else HANGOVER_S

        self._pcm_buf = bytearray()
        self._audio_buf = bytearray()
        self._stream_offset_s = 0.0
        self._is_speaking = False
        self._speech_start_s = None
        self._silence_count = 0
        self._hangover_chunks = int(self._hangover_s * self._sr / self._vad_chunk_samples)
        self._chunk_bytes = int(CHUNK_SECONDS * self._sr * self._bytes_per_sample)
        self._left_context_bytes = int(LEFT_CONTEXT_SECONDS * self._sr * self._bytes_per_sample)
        self._pending_audio = bytearray()
        self._asr_audio_buf = bytearray()
        self._streaming_decoder = None
        self._streaming_failed = False
        self._streaming_text = ""
        self._last_emitted_text = ""

        self._spk_centroids = []
        self._spk_counts = []
        self._last_speaker = 0

        self._vad = _get_vad_model()

    @staticmethod
    def _normalize_pcm16(pcm: bytes) -> bytes:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        peak = np.max(np.abs(samples))
        if peak < 1.0:
            return pcm
        gain = (32767.0 * AGC_TARGET_PEAK) / peak
        if gain <= 1.0:
            return pcm
        normalized = np.clip(samples * gain, -32768, 32767).astype(np.int16)
        return normalized.tobytes()

    async def feed(self, data: bytes):
        self._pcm_buf.extend(data)
        segments = []

        while len(self._pcm_buf) >= self._vad_chunk_bytes:
            vad_chunk = bytes(self._pcm_buf[: self._vad_chunk_bytes])
            del self._pcm_buf[: self._vad_chunk_bytes]

            vad_chunk = self._normalize_pcm16(vad_chunk)

            is_speech = self._run_vad(vad_chunk)
            chunk_dur = self._vad_chunk_samples / self._sr

            self._asr_audio_buf.extend(vad_chunk)

            if is_speech:
                self._silence_count = 0
                if self._speech_start_s is None:
                    self._speech_start_s = self._stream_offset_s
                self._is_speaking = True
                self._pending_audio.extend(vad_chunk)
            else:
                if self._is_speaking or self._speech_start_s is not None:
                    self._pending_audio.extend(vad_chunk)
                if self._is_speaking:
                    self._silence_count += 1
                    if self._silence_count >= self._hangover_chunks:
                        speech_dur = len(self._pending_audio) / (self._sr * self._bytes_per_sample)
                        result = []
                        if speech_dur >= MIN_SPEECH_DURATION_S:
                            await self._drain_streaming_asr(pad_partial=True)
                            result = await self._transcribe_utterance(trim_trailing_word=True)
                            segments.extend(result)
                        self._is_speaking = False
                        if result or not self._streaming_enabled():
                            self._pending_audio.clear()
                            self._speech_start_s = None
                        self._silence_count = 0

            if self._is_speaking:
                speech_dur = len(self._pending_audio) / (self._sr * self._bytes_per_sample)
                if speech_dur >= MAX_SPEECH_DURATION_S:
                    await self._drain_streaming_asr(pad_partial=True)
                    result = await self._transcribe_utterance(trim_trailing_word=True)
                    segments.extend(result)
                    self._pending_audio.clear()
                    self._is_speaking = False
                    self._speech_start_s = None
                    self._silence_count = 0

            self._stream_offset_s += chunk_dur

        await self._drain_streaming_asr(force=False)
        if (
            self._streaming_enabled()
            and not self._is_speaking
            and self._pending_audio
            and self._speech_start_s is not None
        ):
            await self._drain_streaming_asr(pad_partial=True)
            result = await self._transcribe_utterance(trim_trailing_word=True)
            if result:
                segments.extend(result)
                self._pending_audio.clear()
                self._speech_start_s = None

        return segments

    async def flush(self):
        if self._streaming_enabled():
            await self._drain_streaming_asr(force=True)
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
        self._asr_audio_buf.clear()
        self._spk_centroids.clear()
        self._spk_counts.clear()

    def _run_vad(self, chunk: bytes) -> bool:
        if self._vad is None or _torch is None:
            return True
        try:
            audio = _torch.frombuffer(chunk, dtype=_torch.int16).float() / 32768.0
            prob = self._vad(audio, self._sr).item()
            return prob >= self._speech_threshold
        except Exception as e:
            logger.debug(f"VAD inference error: {e}")
            return True

    def _streaming_enabled(self) -> bool:
        if self._streaming_failed or _INFERENCE_MODE == "nim" or _asr_model is None or _torch is None:
            return False
        return hasattr(_asr_model, 'decoding') and hasattr(
            getattr(_asr_model.decoding, 'decoding', None), 'decoding_computer'
        )

    def _get_streaming_decoder(self):
        if self._streaming_decoder is None:
            self._streaming_decoder = _NemoRNNTStreamingDecoder(
                model=_asr_model,
                sample_rate=self._sr,
                chunk_seconds=CHUNK_SECONDS,
                left_context_seconds=LEFT_CONTEXT_SECONDS,
                right_context_seconds=RIGHT_CONTEXT_SECONDS,
            )
        return self._streaming_decoder

    async def _drain_streaming_asr(self, force: bool = False, pad_partial: bool = False):
        if not self._streaming_enabled():
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(_asr_executor, self._drain_streaming_asr_sync, force, pad_partial)
        except Exception as e:
            logger.warning(f"RNNT streaming decode failed, falling back to VAD utterance transcribe: {e}")
            self._streaming_decoder = None
            self._streaming_failed = True
            self._streaming_text = ""
            self._asr_audio_buf.clear()

    def _drain_streaming_asr_sync(self, force: bool, pad_partial: bool = False):
        decoder = self._get_streaming_decoder()
        while True:
            required_bytes = decoder.next_input_bytes(self._bytes_per_sample)
            if len(self._asr_audio_buf) < required_bytes:
                break
            chunk = bytes(self._asr_audio_buf[:required_bytes])
            del self._asr_audio_buf[:required_bytes]
            self._streaming_text = decoder.decode_pcm(chunk, is_last_chunk=False)

        if self._asr_audio_buf:
            if force:
                chunk = bytes(self._asr_audio_buf)
                self._asr_audio_buf.clear()
                self._streaming_text = decoder.decode_pcm(chunk, is_last_chunk=True)
            elif pad_partial:
                required_bytes = decoder.next_input_bytes(self._bytes_per_sample)
                chunk = bytes(self._asr_audio_buf) + b'\x00' * (required_bytes - len(self._asr_audio_buf))
                self._asr_audio_buf.clear()
                self._streaming_text = decoder.decode_pcm(chunk, is_last_chunk=False)

    def _new_streaming_text_since_last_emit(self) -> str:
        text = (self._streaming_text or "").strip()
        emitted = (self._last_emitted_text or "").strip()
        if not text:
            return ""
        if not emitted:
            return text
        if text.startswith(emitted):
            return text[len(emitted) :].strip()

        prev_words = emitted.split()
        new_words = text.split()
        overlap = 0
        for i in range(min(len(prev_words), len(new_words))):
            if prev_words[-(i + 1) :] == new_words[: i + 1]:
                overlap = i + 1
        return " ".join(new_words[overlap:]).strip() if overlap > 0 else text

    async def _transcribe_utterance(self, trim_trailing_word: bool = False):
        speech_pcm = bytes(self._pending_audio)
        speech_start = self._speech_start_s or self._stream_offset_s

        if self._streaming_enabled():
            text = self._new_streaming_text_since_last_emit()
            if not text:
                return []
            if trim_trailing_word:
                words = text.split()
                if len(words) > 1:
                    text = " ".join(words[:-1])
                    self._last_emitted_text = (self._last_emitted_text or "").strip() + " " + text
                else:
                    return []
            else:
                self._last_emitted_text = self._streaming_text.strip()
            dur = len(speech_pcm) / (self._sr * self._bytes_per_sample)
            return self._build_segments(text, speech_start, dur, speech_pcm)

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
