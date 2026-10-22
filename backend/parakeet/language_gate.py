"""Spoken-language gate in front of the Parakeet-25 batch model.

The decision statistic is P(supported): the summed probability of the 25
languages TDT v3 transcribes. Offline (FLEURS 15 languages and the owned
synthetic corpus, 2,349 unsupported clips) MMS-LID-126 gave no unsupported clip
of at least 6 s more than 0.169, and no 3 s crop more than 0.881, so the short
threshold sits above that. The model never sees recognizer text.
"""

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
from scipy.signal import resample_poly  # type: ignore[reportMissingImports]  # scipy ships in the GPU image

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MAX_SECONDS = 30.0
MIN_SECONDS = 1.0
SHORT_SECONDS = 6.0
LONG_THRESHOLD = 0.90
SHORT_THRESHOLD = 0.95

# TDT v3 (nvidia/parakeet-tdt-0.6b-v3) languages; keep equal to the backend's
# prerecorded Parakeet set in config/stt_provider_policy.py.
PARAKEET_LANGUAGES = frozenset('bg hr cs da nl en et fi fr de el hu it lt lv mt pl pt ro ru sk sl es sv uk'.split())

# MMS-LID-126 emits ISO 639-3 labels. Only the codes the gate or its telemetry
# needs are mapped; everything else stays a bounded "other" downstream.
_ISO3_TO_ISO1 = {
    'eng': 'en', 'spa': 'es', 'por': 'pt', 'fra': 'fr', 'deu': 'de', 'rus': 'ru', 'ita': 'it',
    'nld': 'nl', 'pol': 'pl', 'ukr': 'uk', 'ces': 'cs', 'swe': 'sv', 'ron': 'ro', 'hun': 'hu',
    'ell': 'el', 'bul': 'bg', 'dan': 'da', 'fin': 'fi', 'slk': 'sk', 'hrv': 'hr', 'slv': 'sl',
    'lit': 'lt', 'lav': 'lv', 'est': 'et', 'mlt': 'mt',
    'jpn': 'ja', 'cmn': 'zh', 'yue': 'zh', 'kor': 'ko', 'vie': 'vi', 'tha': 'th', 'hin': 'hi',
    'arb': 'ar', 'ara': 'ar', 'ind': 'id', 'tur': 'tr', 'zlm': 'ms', 'msa': 'ms', 'urd': 'ur',
    'ben': 'bn', 'fas': 'fa', 'pes': 'fa',
}  # fmt: skip

MODEL_IDS = {'mms-lid-126': 'facebook/mms-lid-126'}


def configured_model() -> str:
    """The chart selects the model; `off` (and any unknown value) disables the gate rather than guess."""
    value = os.getenv('PARAKEET_LID_MODEL', 'off').strip().lower()
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


class MmsLanguageId:
    """MMS-LID-126 in fp16 on the worker's device. Call only from the GPU worker thread."""

    def __init__(self, model_key: str, device: str) -> None:
        import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
        from transformers import AutoFeatureExtractor, Wav2Vec2ForSequenceClassification  # type: ignore[reportMissingImports]

        repo = MODEL_IDS[model_key]
        self.model_key = model_key
        self._torch: Any = torch
        self._device = device
        self._dtype: Any = torch.float16 if device.startswith('cuda') else torch.float32
        self._extractor: Any = AutoFeatureExtractor.from_pretrained(repo)
        model: Any = Wav2Vec2ForSequenceClassification.from_pretrained(repo, torch_dtype=self._dtype)
        self._model: Any = model.to(device).eval()
        id2label: Dict[int, str] = self._model.config.id2label
        self._labels = [_ISO3_TO_ISO1.get(id2label[i], id2label[i]) for i in range(len(id2label))]

    def probabilities(self, x16k: np.ndarray) -> Dict[str, float]:
        torch = self._torch
        inputs: Any = self._extractor(x16k, sampling_rate=SAMPLE_RATE, return_tensors='pt')
        values = inputs['input_values'].to(self._device, dtype=self._dtype)
        with torch.inference_mode():
            logits = self._model(input_values=values).logits[0].float()
        p = torch.softmax(logits, -1).cpu().numpy()
        out: Dict[str, float] = {}
        for i, label in enumerate(self._labels):
            out[label] = out.get(label, 0.0) + float(p[i])
        return out


def load(device: str) -> Optional[MmsLanguageId]:
    model_key = configured_model()
    if model_key == 'off':
        logger.info('Language gate disabled (PARAKEET_LID_MODEL=off)')
        return None
    model = MmsLanguageId(model_key, device)
    logger.info('Language gate model loaded (model=%s)', model_key)
    return model
