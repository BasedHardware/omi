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
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

logger = logging.getLogger("nllb_translation")

MODEL_DIR = os.environ.get("NLLB_MODEL_DIR", "/models/nllb-200-distilled-600M-ct2-int8")
CT2_DEVICE = os.environ.get("CT2_DEVICE", "cuda")
CT2_COMPUTE_TYPE = os.environ.get("CT2_COMPUTE_TYPE", "int8_float16")
CT2_INTER_THREADS = int(os.environ.get("CT2_INTER_THREADS", "1"))
CT2_INTRA_THREADS = int(os.environ.get("CT2_INTRA_THREADS", "4"))
MAX_INPUT_LENGTH = int(os.environ.get("NLLB_MAX_INPUT_LENGTH", "512"))
MAX_BATCH_SIZE = int(os.environ.get("NLLB_MAX_BATCH_SIZE", "64"))
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

REQUESTS_TOTAL = Counter("nllb_requests_total", "Total translation requests", ["target_lang", "status"])
TRANSLATION_LATENCY = Histogram(
    "nllb_translation_latency_seconds",
    "Translation latency",
    ["target_lang"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)
CHARS_TRANSLATED = Counter("nllb_chars_translated_total", "Total characters translated", ["target_lang"])
ACTIVE_REQUESTS = Gauge("nllb_active_requests", "Active translation requests")
MODEL_LOADED = Gauge("nllb_model_loaded", "Whether model is loaded (1=yes, 0=no)")

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


_inference_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nllb-infer")


def _translate_batch(texts: List[str], source_nllb: str, target_nllb: str) -> List[TranslationResult]:
    if not _translator or not _tokenizer:
        raise RuntimeError("Model not loaded")

    tokenized = [_tokenizer.Encode(text, out_type=str) for text in texts]

    # NLLB requires: source = [src_lang] + tokens + [</s>]
    #                target_prefix = [</s>, tgt_lang]
    if source_nllb:
        tokenized = [[source_nllb] + tokens + ["</s>"] for tokens in tokenized]
    else:
        tokenized = [tokens + ["</s>"] for tokens in tokenized]

    target_prefix = [["</s>", target_nllb]] * len(texts)

    results = _translator.translate_batch(
        tokenized,
        target_prefix=target_prefix,
        max_input_length=MAX_INPUT_LENGTH,
        beam_size=4,
    )

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
            partial(_translate_batch, req.contents, source_nllb or "", target_nllb),
        )
        latency = time.monotonic() - t0

        REQUESTS_TOTAL.labels(target_lang=req.target_language_code, status="ok").inc()
        TRANSLATION_LATENCY.labels(target_lang=req.target_language_code).observe(latency)
        CHARS_TRANSLATED.labels(target_lang=req.target_language_code).inc(total_chars)

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
    return {"status": "ok", "model_loaded": _translator is not None}


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
