import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from typing import Dict, List, Optional

import ctranslate2
import sentencepiece as spm
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter as PromCounter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
from starlette.responses import Response

logger = logging.getLogger("nllb_translation")


def _counter(name: str, doc: str, labels: List[str]) -> PromCounter:
    try:
        return PromCounter(name, doc, labels)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def _histogram(name: str, doc: str, labels: List[str], buckets: List[float]) -> Histogram:
    try:
        return Histogram(name, doc, labels, buckets=buckets)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def _gauge(name: str, doc: str) -> Gauge:
    try:
        return Gauge(name, doc)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def _histogram_no_labels(name: str, doc: str, buckets: List[float]) -> Histogram:
    try:
        return Histogram(name, doc, buckets=buckets)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


MODEL_DIR = os.environ.get("NLLB_MODEL_DIR", "/models/nllb-200-distilled-600M-ct2-int8")
CT2_DEVICE = os.environ.get("CT2_DEVICE", "cuda")
CT2_COMPUTE_TYPE = os.environ.get("CT2_COMPUTE_TYPE", "int8_float16")
CT2_INTER_THREADS = int(os.environ.get("CT2_INTER_THREADS", "1"))
CT2_INTRA_THREADS = int(os.environ.get("CT2_INTRA_THREADS", "4"))
MAX_INPUT_LENGTH = int(os.environ.get("NLLB_MAX_INPUT_LENGTH", "512"))
MAX_BATCH_SIZE = int(os.environ.get("NLLB_MAX_BATCH_SIZE", "64"))
BEAM_SIZE = int(os.environ.get("NLLB_BEAM_SIZE", "1"))
INFERENCE_WORKERS = int(os.environ.get("NLLB_INFERENCE_WORKERS", "2"))
PORT = int(os.environ.get("PORT", "8080"))

BCP47_TO_NLLB: Dict[str, str] = {
    "en": "eng_Latn",
    "es": "spa_Latn",
    "zh": "zho_Hans",
    "zh-CN": "zho_Hans",
    "zh-Hans": "zho_Hans",
    "zh-TW": "zho_Hant",
    "zh-Hant": "zho_Hant",
    "hi": "hin_Deva",
    "pt": "por_Latn",
    "pt-BR": "por_Latn",
    "ru": "rus_Cyrl",
    "ja": "jpn_Jpan",
    "de": "deu_Latn",
    "ar": "arb_Arab",
    "fr": "fra_Latn",
    "it": "ita_Latn",
    "ko": "kor_Hang",
    "nl": "nld_Latn",
    "th": "tha_Thai",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "ur": "urd_Arab",
    "vi": "vie_Latn",
}

NLLB_TO_BCP47: Dict[str, str] = {}
for bcp, nllb in BCP47_TO_NLLB.items():
    if nllb not in NLLB_TO_BCP47:
        NLLB_TO_BCP47[nllb] = bcp.split("-")[0]

_BCP47_TO_NLLB_LOWER: Dict[str, str] = {k.lower(): v for k, v in BCP47_TO_NLLB.items()}

REQUESTS_TOTAL = _counter("nllb_requests_total", "Total translation requests", ["target_lang", "status"])
TRANSLATION_LATENCY = _histogram(
    "nllb_translation_latency_seconds",
    "Translation latency",
    ["target_lang"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)
CHARS_TRANSLATED = _counter("nllb_chars_translated_total", "Total characters translated", ["target_lang"])
SENTENCES_TRANSLATED = _counter("nllb_sentences_translated_total", "Total sentences translated", ["target_lang"])
ACTIVE_REQUESTS = _gauge("nllb_active_requests", "Active translation requests")
MODEL_LOADED = _gauge("nllb_model_loaded", "Whether model is loaded (1=yes, 0=no)")
BATCH_SIZE = _histogram_no_labels(
    "nllb_batch_size",
    "Number of sentences per translate request",
    buckets=[1, 2, 5, 10, 20, 32, 50, 64, 100],
)
INFERENCE_LATENCY = _histogram(
    "nllb_inference_latency_seconds",
    "Pure CTranslate2 inference latency (excludes tokenization)",
    ["target_lang"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)
TOKENIZATION_LATENCY = _histogram_no_labels(
    "nllb_tokenization_latency_seconds",
    "SentencePiece tokenization latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)
QUEUE_WAIT = _histogram_no_labels(
    "nllb_request_queue_duration_seconds",
    "Time from request received to inference start (queue wait)",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)
MODEL_LOAD_DURATION = _gauge("nllb_model_load_duration_seconds", "Time taken to load the model on last startup")

_translator: Optional[ctranslate2.Translator] = None
_tokenizer: Optional[spm.SentencePieceProcessor] = None


def _load_model():
    global _translator, _tokenizer
    logger.info("Loading CTranslate2 model from %s (device=%s, compute=%s)", MODEL_DIR, CT2_DEVICE, CT2_COMPUTE_TYPE)
    t0 = time.monotonic()
    _translator = ctranslate2.Translator(
        MODEL_DIR,
        device=CT2_DEVICE,
        compute_type=CT2_COMPUTE_TYPE,
        inter_threads=CT2_INTER_THREADS,
        intra_threads=CT2_INTRA_THREADS,
    )
    sp_model_path = os.path.join(MODEL_DIR, "sentencepiece.model")
    if not os.path.exists(sp_model_path):
        sp_model_path = os.path.join(MODEL_DIR, "sentencepiece.bpe.model")
    _tokenizer = spm.SentencePieceProcessor()
    _tokenizer.Load(sp_model_path)
    elapsed = time.monotonic() - t0
    MODEL_LOADED.set(1)
    MODEL_LOAD_DURATION.set(elapsed)
    logger.info("Model loaded in %.1fs", elapsed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_model()
    yield
    MODEL_LOADED.set(0)


app = FastAPI(title="NLLB Translation Service", lifespan=lifespan)


class TranslateRequest(BaseModel):
    contents: List[str] = Field(..., max_length=MAX_BATCH_SIZE)
    target_language_code: str
    source_language_code: Optional[str] = None
    request_id: Optional[str] = None


class TranslationResult(BaseModel):
    translated_text: str
    detected_language_code: str


class TranslateResponse(BaseModel):
    translations: List[TranslationResult]
    model: str = "facebook/nllb-200-distilled-600M"
    latency_ms: float


def _resolve_nllb_code(bcp47_code: str) -> Optional[str]:
    if not bcp47_code:
        return None
    code = bcp47_code.strip().lower()
    if code in _BCP47_TO_NLLB_LOWER:
        return _BCP47_TO_NLLB_LOWER[code]
    base = code.split("-")[0]
    if base in _BCP47_TO_NLLB_LOWER:
        return _BCP47_TO_NLLB_LOWER[base]
    if code in NLLB_TO_BCP47:
        return code
    return None


_inference_pool = ThreadPoolExecutor(max_workers=INFERENCE_WORKERS, thread_name_prefix="nllb-infer")


def _translate_batch(
    texts: List[str], source_nllb: str, target_nllb: str, t_queued: float = 0.0
) -> List[TranslationResult]:
    if t_queued > 0:
        QUEUE_WAIT.observe(time.monotonic() - t_queued)
    if not _translator or not _tokenizer:
        raise RuntimeError("Model not loaded")

    t_tok = time.monotonic()
    tokenized = [_tokenizer.Encode(text, out_type=str) for text in texts]

    if source_nllb:
        tokenized = [[source_nllb] + tokens + ["</s>"] for tokens in tokenized]
    else:
        tokenized = [tokens + ["</s>"] for tokens in tokenized]

    target_prefix = [["</s>", target_nllb]] * len(texts)
    TOKENIZATION_LATENCY.observe(time.monotonic() - t_tok)

    t_inf = time.monotonic()
    results = _translator.translate_batch(
        tokenized,
        target_prefix=target_prefix,
        max_input_length=MAX_INPUT_LENGTH,
        beam_size=BEAM_SIZE,
    )
    target_bcp47 = NLLB_TO_BCP47.get(target_nllb, target_nllb.split("_")[0])
    INFERENCE_LATENCY.labels(target_lang=target_bcp47).observe(time.monotonic() - t_inf)

    special_tokens = {"</s>", target_nllb}
    translations = []
    source_bcp47 = NLLB_TO_BCP47.get(source_nllb, source_nllb.split("_")[0] if source_nllb else "")
    for result in results:
        tokens = [t for t in result.hypotheses[0] if t not in special_tokens]
        decoded = _tokenizer.Decode(tokens)
        translations.append(
            TranslationResult(
                translated_text=decoded,
                detected_language_code=source_bcp47,
            )
        )
    return translations


@app.post("/v1/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    t_queued = time.monotonic()
    ACTIVE_REQUESTS.inc()
    try:
        target_nllb = _resolve_nllb_code(req.target_language_code)
        if not target_nllb:
            REQUESTS_TOTAL.labels(target_lang=req.target_language_code, status="unsupported_target").inc()
            raise HTTPException(status_code=400, detail=f"Unsupported target language: {req.target_language_code}")

        source_nllb = _resolve_nllb_code(req.source_language_code) if req.source_language_code else None
        if req.source_language_code and not source_nllb:
            REQUESTS_TOTAL.labels(target_lang=req.target_language_code, status="unsupported_source").inc()
            raise HTTPException(status_code=400, detail=f"Unsupported source language: {req.source_language_code}")

        if not req.contents:
            return TranslateResponse(translations=[], latency_ms=0)

        total_chars = sum(len(c) for c in req.contents)
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()
        translations = await loop.run_in_executor(
            _inference_pool,
            partial(_translate_batch, req.contents, source_nllb or "", target_nllb, t_queued),
        )
        latency = time.monotonic() - t0

        REQUESTS_TOTAL.labels(target_lang=req.target_language_code, status="ok").inc()
        TRANSLATION_LATENCY.labels(target_lang=req.target_language_code).observe(latency)
        CHARS_TRANSLATED.labels(target_lang=req.target_language_code).inc(total_chars)
        SENTENCES_TRANSLATED.labels(target_lang=req.target_language_code).inc(len(req.contents))
        BATCH_SIZE.observe(len(req.contents))

        return TranslateResponse(
            translations=translations,
            latency_ms=round(latency * 1000, 1),
        )
    except HTTPException:
        raise
    except Exception as e:
        REQUESTS_TOTAL.labels(target_lang=req.target_language_code, status="error").inc()
        logger.error("Translation error: %s", e)
        raise HTTPException(status_code=500, detail="Internal translation error")
    finally:
        ACTIVE_REQUESTS.dec()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _translator is not None,
        "model_dir": MODEL_DIR,
        "beam_size": BEAM_SIZE,
        "compute_type": CT2_COMPUTE_TYPE,
        "inter_threads": CT2_INTER_THREADS,
        "intra_threads": CT2_INTRA_THREADS,
        "max_batch_size": MAX_BATCH_SIZE,
        "inference_workers": INFERENCE_WORKERS,
    }


@app.get("/ready")
async def ready():
    if _translator is None or _tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
