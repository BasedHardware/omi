"""Spoken-language gate in front of the Parakeet-25 batch model.

The decision statistic is P(supported): the summed probability of the 25
languages TDT v3 transcribes, from Whisper-base's language-token head (Apache-2.0;
MMS-LID is CC-BY-NC and cannot serve a commercial product). Offline (FLEURS 15
languages x 60 clips and the owned synthetic corpus, 2,349 unsupported clips)
Whisper-base's highest P(supported) on unsupported speech was 0.922 at >=6 s
(Hindi read as Romanian) and 0.978 on a 3 s crop (Indonesian as Italian); the
thresholds sit above both. The model never sees
recognizer text and never decodes past the language token.
"""

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

import numpy as np
from scipy.signal import resample_poly  # type: ignore[reportMissingImports]  # scipy ships in the GPU image

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MAX_SECONDS = 30.0
MIN_SECONDS = 1.0
SHORT_SECONDS = 6.0
LONG_THRESHOLD = 0.95
SHORT_THRESHOLD = 0.985

# TDT v3 (nvidia/parakeet-tdt-0.6b-v3) languages; keep equal to the backend's
# prerecorded Parakeet set in config/stt_provider_policy.py.
PARAKEET_LANGUAGES = frozenset('bg hr cs da nl en et fi fr de el hu it lt lv mt pl pt ro ru sk sl es sv uk'.split())

# Whisper language tokens that differ from ISO 639-1 codes elsewhere in Omi.
_WHISPER_ALIASES = {'iw': 'he', 'jw': 'jv', 'yue': 'zh'}

MODEL_IDS = {'whisper-base': 'openai/whisper-base'}


def configured_model() -> str:
    """Default whisper-base; `off` (and any unknown value) disables the gate rather than guess."""
    value = os.getenv('PARAKEET_LID_MODEL', 'whisper-base').strip().lower()
    return value if value in MODEL_IDS else 'off'


def threshold_for(seconds: float) -> float:
    return LONG_THRESHOLD if seconds >= SHORT_SECONDS else SHORT_THRESHOLD


@dataclass(frozen=True)
class LanguageVerdict:
    route: str
    p_supported: float
    language: str
    language_probability: float
    audio_seconds: float
    threshold: float
    model: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            'route': self.route,
            'p_supported': round(self.p_supported, 6),
            'language': self.language,
            'language_probability': round(self.language_probability, 6),
            'audio_seconds': round(self.audio_seconds, 3),
            'threshold': self.threshold,
            'model': self.model,
        }


def decide(probabilities: Dict[str, float], audio_seconds: float, model: str) -> LanguageVerdict:
    """Pure routing rule over per-language probabilities (ISO 639-1 keys)."""
    threshold = threshold_for(audio_seconds)
    finite = {k: v for k, v in probabilities.items() if isinstance(v, float) and math.isfinite(v) and v >= 0}
    p_supported = min(1.0, sum(v for k, v in finite.items() if k in PARAKEET_LANGUAGES))
    top = max(finite, key=lambda k: finite[k]) if finite else 'und'
    top_p = finite.get(top, 0.0)
    parakeet = audio_seconds >= MIN_SECONDS and p_supported >= threshold
    return LanguageVerdict(
        route='parakeet' if parakeet else 'multilingual',
        p_supported=p_supported,
        language=top,
        language_probability=top_p,
        audio_seconds=audio_seconds,
        threshold=threshold,
        model=model,
    )


def to_mono_16k(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """First MAX_SECONDS of float32 mono 16 kHz audio."""
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    x = x[: int(MAX_SECONDS * sample_rate)]
    if sample_rate != SAMPLE_RATE and x.size:
        g = math.gcd(SAMPLE_RATE, sample_rate)
        x = resample_poly(x, SAMPLE_RATE // g, sample_rate // g).astype(np.float32)
    return x


class WhisperLanguageId:
    """Whisper encoder plus one decoder step; softmax over language tokens only. GPU worker thread only."""

    def __init__(self, model_key: str, device: str) -> None:
        import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
        from transformers import WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperTokenizer  # type: ignore[reportMissingImports]
        from transformers.models.whisper.tokenization_whisper import LANGUAGES  # type: ignore[reportMissingImports]

        repo = MODEL_IDS[model_key]
        self.model_key = model_key
        self._torch: Any = torch
        self._device = device
        self._dtype: Any = torch.float16 if device.startswith('cuda') else torch.float32
        self._extractor: Any = WhisperFeatureExtractor.from_pretrained(repo)
        tokenizer: Any = WhisperTokenizer.from_pretrained(repo)
        model: Any = WhisperForConditionalGeneration.from_pretrained(repo, torch_dtype=self._dtype)
        self._model: Any = model.to(device).eval()
        codes: List[str] = sorted(cast(Dict[str, str], LANGUAGES))
        self._token_ids = torch.tensor(
            tokenizer.convert_tokens_to_ids([f'<|{code}|>' for code in codes]), device=device
        )
        self._labels: List[str] = [_WHISPER_ALIASES.get(code, code) for code in codes]
        self._start = torch.tensor([[tokenizer.convert_tokens_to_ids('<|startoftranscript|>')]], device=device)

    def probabilities(self, x16k: np.ndarray) -> Dict[str, float]:
        torch = self._torch
        features: Any = self._extractor(x16k, sampling_rate=SAMPLE_RATE, return_tensors='pt').input_features
        with torch.inference_mode():
            logits = self._model(
                input_features=features.to(self._device, dtype=self._dtype), decoder_input_ids=self._start
            ).logits[0, -1]
            p = torch.softmax(logits[self._token_ids].float(), -1).cpu().numpy()
        out: Dict[str, float] = {}
        for i, label in enumerate(self._labels):
            out[label] = out.get(label, 0.0) + float(p[i])
        return out


def load(device: str) -> Optional[WhisperLanguageId]:
    model_key = configured_model()
    if model_key == 'off':
        logger.info('Language gate disabled (PARAKEET_LID_MODEL=off)')
        return None
    model = WhisperLanguageId(model_key, device)
    logger.info('Language gate model loaded (model=%s)', model_key)
    return model
