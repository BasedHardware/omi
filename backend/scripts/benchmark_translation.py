#!/usr/bin/env python3
"""Benchmark NLLB self-hosted translation against Google Cloud Translation V3.

Uses FLORES-200 devtest (1012 sentences) as reference corpus, evaluating with
COMET (primary), chrF++, and BLEU. Languages are grouped into tiers (high/medium/low
resource) following geni's MT benchmark methodology.

Usage:
    # Install dependencies
    pip install datasets sacrebleu unbabel-comet httpx google-cloud-translate

    # Dry run — validate dataset loading and language pairs
    python3 scripts/benchmark_translation.py --dry-run

    # Full benchmark (NLLB must be deployed)
    python3 scripts/benchmark_translation.py \
        --nllb-url http://nllb-translation:8080 \
        --output-dir /tmp/benchmark-results

    # Skip Google (use cached results from previous run)
    python3 scripts/benchmark_translation.py \
        --nllb-url http://nllb-translation:8080 \
        --skip-google \
        --output-dir /tmp/benchmark-results

    # Specific languages only
    python3 scripts/benchmark_translation.py \
        --nllb-url http://nllb-translation:8080 \
        --languages es,zh,ja,ko
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("benchmark_translation")

LANG_TIERS: Dict[str, List[str]] = {
    "high": ["es", "zh", "fr", "de", "pt", "ru", "ja", "ko", "it", "ar"],
    "medium": ["nl", "tr", "th", "vi", "uk", "hi"],
    "low": ["ur", "zh-TW"],
}

ALL_TARGET_LANGUAGES: List[str] = []
for _tier_langs in LANG_TIERS.values():
    ALL_TARGET_LANGUAGES.extend(_tier_langs)

BCP47_TO_FLORES = {
    "en": "eng_Latn",
    "es": "spa_Latn",
    "zh": "zho_Hans",
    "zh-TW": "zho_Hant",
    "hi": "hin_Deva",
    "pt": "por_Latn",
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


def get_tier(lang: str) -> str:
    for tier, langs in LANG_TIERS.items():
        if lang in langs:
            return tier
    return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark NLLB vs Google Cloud Translation on FLORES-200 devtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--nllb-url", type=str, default="http://localhost:8080", help="Base URL of NLLB service")
    parser.add_argument(
        "--languages",
        type=str,
        default=",".join(ALL_TARGET_LANGUAGES),
        help="Comma-separated BCP-47 target language codes",
    )
    parser.add_argument("--output-dir", type=str, default="/tmp/benchmark-results", help="Output directory for results")
    parser.add_argument(
        "--samples", type=int, default=0, help="Number of sentences per pair (0 = all 1012 from devtest)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without running translations")
    parser.add_argument("--skip-google", action="store_true", help="Skip Google Translate (use cached if available)")
    parser.add_argument("--skip-comet", action="store_true", help="Skip COMET metric (requires GPU, slow)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for API calls")
    parser.add_argument(
        "--cache-dir", type=str, default="/tmp/benchmark-translation-cache", help="Cache dir for Google responses"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


BCP47_TO_WMT = {
    "de": "de",
    "zh": "zh",
    "ru": "ru",
    "ja": "ja",
    "uk": "uk",
}

WMT_TESTSET = "wmt22"


def load_flores_devtest(languages: List[str]) -> Dict[str, List[str]]:
    """Load FLORES-200 devtest sentences from HuggingFace.

    Requires HF_TOKEN set (FLORES-200 is a gated dataset). Falls back to
    load_wmt_testset() if FLORES is unavailable.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        logger.warning("datasets library not installed, falling back to WMT")
        return {}

    logger.info("Loading FLORES-200 devtest from HuggingFace...")
    needed_flores = ["eng_Latn"]
    for lang in languages:
        flores = BCP47_TO_FLORES.get(lang)
        if flores:
            needed_flores.append(flores)

    result: Dict[str, List[str]] = {}
    for flores_code in needed_flores:
        try:
            ds = load_dataset("facebook/flores", flores_code, split="devtest")
            sentences = [row["sentence"] for row in ds]
            result[flores_code] = sentences
            logger.info("  %s: %d sentences", flores_code, len(sentences))
        except Exception as e:
            logger.warning("  %s: failed (%s)", flores_code, e)
            if not result:
                logger.info("FLORES-200 unavailable (gated dataset, set HF_TOKEN). Falling back to WMT.")
                return {}

    return result


def load_wmt_testset(languages: List[str]) -> Dict[str, List[str]]:
    """Load WMT22 test set via sacrebleu as fallback when FLORES-200 is unavailable.

    WMT covers fewer language pairs than FLORES but requires no authentication.
    """
    try:
        import sacrebleu
    except ImportError:
        logger.error("sacrebleu not installed: pip install sacrebleu")
        return {}

    available_pairs = sacrebleu.get_langpairs_for_testset(WMT_TESTSET)
    logger.info("Loading %s test set (available pairs: %s)", WMT_TESTSET, ", ".join(sorted(available_pairs)))

    result: Dict[str, List[str]] = {}

    for lang in languages:
        wmt_code = BCP47_TO_WMT.get(lang)
        if not wmt_code:
            continue
        pair = f"en-{wmt_code}"
        if pair not in available_pairs:
            continue

        try:
            src_file = sacrebleu.get_source_file(WMT_TESTSET, pair)
            ref_files = sacrebleu.get_reference_files(WMT_TESTSET, pair)

            with open(src_file, 'r', encoding='utf-8') as f:
                src_sentences = [line.strip() for line in f if line.strip()]
            with open(ref_files[0], 'r', encoding='utf-8') as f:
                ref_sentences = [line.strip() for line in f if line.strip()]

            flores_src = BCP47_TO_FLORES["en"]
            flores_tgt = BCP47_TO_FLORES.get(lang, lang)

            if flores_src not in result:
                result[flores_src] = src_sentences
            result[flores_tgt] = ref_sentences
            logger.info("  %s (en->%s): %d sentences from %s", flores_tgt, wmt_code, len(ref_sentences), WMT_TESTSET)
        except Exception as e:
            logger.warning("  en->%s: failed (%s)", wmt_code, e)

    return result


def _cache_key(text: str, target_lang: str) -> str:
    return hashlib.sha256(f"{target_lang}:{text}".encode()).hexdigest()


def _load_google_cache(cache_dir: str, target_lang: str) -> Dict[str, str]:
    cache_file = Path(cache_dir) / f"google_{target_lang}.json"
    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_google_cache(cache_dir: str, target_lang: str, cache: Dict[str, str]) -> None:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"google_{target_lang}.json"
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)


def translate_nllb_batch(
    client: httpx.Client, texts: List[str], target_lang: str, source_lang: str = "en"
) -> Tuple[List[str], float]:
    """Call self-hosted NLLB translation service. Returns (translations, latency_seconds)."""
    t0 = time.monotonic()
    resp = client.post(
        "/v1/translate",
        json={
            "contents": texts,
            "target_language_code": target_lang,
            "source_language_code": source_lang,
        },
        timeout=120.0,
    )
    latency = time.monotonic() - t0

    if resp.status_code != 200:
        logger.error("NLLB error: status=%d body=%s", resp.status_code, resp.text[:200])
        return [""] * len(texts), latency

    data = resp.json()
    translations = [t.get("translated_text", "") for t in data.get("translations", [])]
    return translations, latency


def translate_google_batch(texts: List[str], target_lang: str, cache_dir: str) -> Tuple[List[str], float]:
    """Call Google Cloud Translation V3. Caches responses to avoid re-billing."""
    try:
        from google.cloud import translate_v3
    except ImportError:
        logger.error("Install: pip install google-cloud-translate")
        return [""] * len(texts), 0.0

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT env var not set")
        return [""] * len(texts), 0.0

    cache = _load_google_cache(cache_dir, target_lang)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []
    results = [""] * len(texts)

    for i, text in enumerate(texts):
        key = _cache_key(text, target_lang)
        if key in cache:
            results[i] = cache[key]
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    if not uncached_texts:
        logger.info("  All %d sentences served from cache", len(texts))
        return results, 0.0

    logger.info("  %d cached, %d to translate via Google", len(texts) - len(uncached_texts), len(uncached_texts))

    client = translate_v3.TranslationServiceClient()
    parent = f"projects/{project_id}/locations/global"

    total_latency = 0.0
    api_batch_size = 128
    for batch_start in range(0, len(uncached_texts), api_batch_size):
        batch = uncached_texts[batch_start : batch_start + api_batch_size]
        batch_indices = uncached_indices[batch_start : batch_start + api_batch_size]

        t0 = time.monotonic()
        response = client.translate_text(
            contents=batch,
            parent=parent,
            mime_type="text/plain",
            target_language_code=target_lang,
        )
        total_latency += time.monotonic() - t0

        for j, translation in enumerate(response.translations):
            idx = batch_indices[j]
            results[idx] = translation.translated_text
            key = _cache_key(uncached_texts[batch_start + j], target_lang)
            cache[key] = translation.translated_text

    _save_google_cache(cache_dir, target_lang, cache)
    return results, total_latency


def compute_bleu(hypotheses: List[str], references: List[str]) -> Optional[float]:
    """Corpus-level BLEU via sacrebleu."""
    try:
        import sacrebleu
    except ImportError:
        logger.warning("sacrebleu not installed: pip install sacrebleu")
        return None

    bleu = sacrebleu.corpus_bleu(hypotheses, [references])
    return round(bleu.score, 2)


def compute_chrf_pp(hypotheses: List[str], references: List[str]) -> Optional[float]:
    """Corpus-level chrF++ (character + word n-grams)."""
    try:
        import sacrebleu
    except ImportError:
        logger.warning("sacrebleu not installed: pip install sacrebleu")
        return None

    chrf = sacrebleu.corpus_chrf(hypotheses, [references], word_order=2)
    return round(chrf.score, 2)


def compute_comet(sources: List[str], hypotheses: List[str], references: List[str]) -> Optional[float]:
    """COMET score using wmt22-comet-da (best correlation with human judgment)."""
    try:
        from comet import download_model, load_from_checkpoint
    except ImportError:
        logger.warning("unbabel-comet not installed: pip install unbabel-comet")
        return None

    model_path = download_model("Unbabel/wmt22-comet-da")
    model = load_from_checkpoint(model_path)
    data = [{"src": s, "mt": h, "ref": r} for s, h, r in zip(sources, hypotheses, references)]
    output = model.predict(data, batch_size=32, gpus=1 if _has_gpu() else 0)
    score = output.system_score if hasattr(output, 'system_score') else output[1]
    return round(float(score), 4)


def _has_gpu() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


def paired_bootstrap_significance(
    sys_a_scores: List[float], sys_b_scores: List[float], n_resamples: int = 1000
) -> float:
    """Paired bootstrap resampling for statistical significance.

    Returns p-value: probability that sys_a is NOT better than sys_b.
    """
    import random

    n = len(sys_a_scores)
    if n != len(sys_b_scores) or n == 0:
        return 1.0

    delta_real = sum(sys_a_scores) / n - sum(sys_b_scores) / n
    count_worse = 0

    for _ in range(n_resamples):
        indices = [random.randint(0, n - 1) for _ in range(n)]
        a_mean = sum(sys_a_scores[i] for i in indices) / n
        b_mean = sum(sys_b_scores[i] for i in indices) / n
        if (a_mean - b_mean) <= 0:
            count_worse += 1

    return count_worse / n_resamples


def run_benchmark_for_pair(
    nllb_client: Optional[httpx.Client],
    target_lang: str,
    source_sentences: List[str],
    reference_sentences: List[str],
    batch_size: int,
    skip_google: bool,
    skip_comet: bool,
    cache_dir: str,
) -> Dict[str, Any]:
    """Run benchmark for one language pair (en -> target_lang)."""
    n = min(len(source_sentences), len(reference_sentences))
    sources = source_sentences[:n]
    refs = reference_sentences[:n]

    result: Dict[str, Any] = {
        "target_lang": target_lang,
        "tier": get_tier(target_lang),
        "num_sentences": n,
        "nllb": {"translations": [], "latency_seconds": 0.0, "metrics": {}},
        "google": {"translations": [], "latency_seconds": 0.0, "metrics": {}},
    }

    if nllb_client:
        logger.info("  NLLB translating %d sentences...", n)
        all_nllb: List[str] = []
        total_latency = 0.0
        for i in range(0, n, batch_size):
            batch = sources[i : i + batch_size]
            translations, latency = translate_nllb_batch(nllb_client, batch, target_lang)
            all_nllb.extend(translations)
            total_latency += latency

        result["nllb"]["translations"] = all_nllb
        result["nllb"]["latency_seconds"] = round(total_latency, 3)
        result["nllb"]["chars_per_second"] = round(sum(len(s) for s in sources) / max(total_latency, 0.001))

        bleu = compute_bleu(all_nllb, refs)
        chrf = compute_chrf_pp(all_nllb, refs)
        comet = compute_comet(sources, all_nllb, refs) if not skip_comet else None
        result["nllb"]["metrics"] = {"bleu": bleu, "chrf_pp": chrf, "comet": comet}
        logger.info(
            "  NLLB en->%s: BLEU=%.1f chrF++=%.1f latency=%.1fs",
            target_lang,
            bleu or 0,
            chrf or 0,
            total_latency,
        )

    if not skip_google:
        logger.info("  Google translating %d sentences...", n)
        all_google, total_latency = translate_google_batch(sources, target_lang, cache_dir)
        result["google"]["translations"] = all_google
        result["google"]["latency_seconds"] = round(total_latency, 3)

        bleu = compute_bleu(all_google, refs)
        chrf = compute_chrf_pp(all_google, refs)
        comet = compute_comet(sources, all_google, refs) if not skip_comet else None
        result["google"]["metrics"] = {"bleu": bleu, "chrf_pp": chrf, "comet": comet}
        logger.info("  Google en->%s: BLEU=%.1f chrF++=%.1f", target_lang, bleu or 0, chrf or 0)

    return result


def write_report(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """Write JSON report (without translations) and formatted summary."""
    report_slim = []
    for r in results:
        entry = {
            "target_lang": r["target_lang"],
            "tier": r["tier"],
            "num_sentences": r["num_sentences"],
            "nllb": {
                "latency_seconds": r["nllb"]["latency_seconds"],
                "chars_per_second": r["nllb"].get("chars_per_second"),
                "metrics": r["nllb"]["metrics"],
            },
            "google": {
                "latency_seconds": r["google"]["latency_seconds"],
                "metrics": r["google"]["metrics"],
            },
        }
        report_slim.append(entry)

    json_path = output_dir / "benchmark_report.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(
            {"benchmark": "nllb-vs-google-flores200", "source": "en", "results": report_slim},
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("JSON report: %s", json_path)


def _fmt(v: Optional[float], w: int = 7) -> str:
    if v is not None:
        return f"{v:{w}.1f}"
    return f"{'--':>{w}}"


def _fmt4(v: Optional[float], w: int = 8) -> str:
    if v is not None:
        return f"{v:{w}.4f}"
    return f"{'--':>{w}}"


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Print formatted summary table grouped by tier."""
    header = (
        f"{'Lang':>6s} {'Tier':>6s}  "
        f"{'NLLB BLEU':>9s} {'G BLEU':>7s} {'d':>6s}  "
        f"{'NLLB chrF++':>11s} {'G chrF++':>8s} {'d':>6s}  "
        f"{'NLLB COMET':>10s} {'G COMET':>8s}"
    )
    sep = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print("BENCHMARK: NLLB-200-distilled-600M vs Google Cloud Translation V3")
    print("Corpus: FLORES-200 devtest | Source: English")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)

    for tier in ["high", "medium", "low"]:
        tier_results = [r for r in results if r["tier"] == tier]
        if not tier_results:
            continue

        for r in tier_results:
            nm = r["nllb"]["metrics"]
            gm = r["google"]["metrics"]

            nb = nm.get("bleu")
            gb = gm.get("bleu")
            nc = nm.get("chrf_pp")
            gc = gm.get("chrf_pp")
            ncomet = nm.get("comet")
            gcomet = gm.get("comet")

            d_bleu = f"{nb - gb:+.1f}" if nb is not None and gb is not None else ""
            d_chrf = f"{nc - gc:+.1f}" if nc is not None and gc is not None else ""

            print(
                f"{r['target_lang']:>6s} {tier:>6s}  "
                f"{_fmt(nb, 9)} {_fmt(gb, 7)} {d_bleu:>6s}  "
                f"{_fmt(nc, 11)} {_fmt(gc, 8)} {d_chrf:>6s}  "
                f"{_fmt4(ncomet, 10)} {_fmt4(gcomet, 8)}"
            )

        tier_nbleu = [
            r["nllb"]["metrics"]["bleu"] for r in tier_results if r["nllb"]["metrics"].get("bleu") is not None
        ]
        tier_gbleu = [
            r["google"]["metrics"]["bleu"] for r in tier_results if r["google"]["metrics"].get("bleu") is not None
        ]
        if tier_nbleu and tier_gbleu:
            avg_n = sum(tier_nbleu) / len(tier_nbleu)
            avg_g = sum(tier_gbleu) / len(tier_gbleu)
            pct = ((avg_n - avg_g) / avg_g * 100) if avg_g else 0
            print(f"  {'avg':>4s} {tier:>6s}  {avg_n:9.1f} {avg_g:7.1f} {avg_n - avg_g:+6.1f}  ({pct:+.0f}%)")
        print(sep)

    all_nbleu = [r["nllb"]["metrics"]["bleu"] for r in results if r["nllb"]["metrics"].get("bleu") is not None]
    all_gbleu = [r["google"]["metrics"]["bleu"] for r in results if r["google"]["metrics"].get("bleu") is not None]
    if all_nbleu and all_gbleu:
        avg_n = sum(all_nbleu) / len(all_nbleu)
        avg_g = sum(all_gbleu) / len(all_gbleu)
        pct = ((avg_n - avg_g) / avg_g * 100) if avg_g else 0
        print(f"  {'OVERALL AVG':>12s}  {avg_n:9.1f} {avg_g:7.1f} {avg_n - avg_g:+6.1f}  ({pct:+.0f}%)")
    print(f"{'=' * len(header)}")


def dry_run(args: argparse.Namespace) -> int:
    """Validate dataset loading, dependencies, and services."""
    languages = [lang.strip() for lang in args.languages.split(",")]

    print(f"\n{'=' * 60}")
    print("BENCHMARK DRY RUN")
    print(f"{'=' * 60}")
    print(f"Target languages: {len(languages)} ({', '.join(languages)})")
    print(f"NLLB URL:         {args.nllb_url}")
    print(f"Skip Google:      {args.skip_google}")
    print(f"Skip COMET:       {args.skip_comet}")
    print()

    issues: List[str] = []

    print("  Dataset:")
    flores_ok = False
    try:
        from datasets import load_dataset

        ds = load_dataset("facebook/flores", "eng_Latn", split="devtest")
        print(f"    [OK]   FLORES-200 devtest: {len(ds)} English sentences")
        flores_ok = True
    except Exception as e:
        print(f"    [WARN] FLORES-200: {e}")

    wmt_data = load_wmt_testset(languages) if not flores_ok else {}
    if not flores_ok and wmt_data:
        en_key = BCP47_TO_FLORES["en"]
        n = len(wmt_data.get(en_key, []))
        wmt_langs = sum(1 for k in wmt_data if k != en_key)
        print(f"    [OK]   WMT22 fallback: {n} English sentences, {wmt_langs} target languages")
    elif not flores_ok and not wmt_data:
        issues.append("No dataset available (set HF_TOKEN for FLORES-200, or install sacrebleu for WMT)")

    print(f"\n  Language pairs:")
    for lang in languages:
        flores = BCP47_TO_FLORES.get(lang)
        wmt = BCP47_TO_WMT.get(lang)
        if flores_ok:
            try:
                ds = load_dataset("facebook/flores", flores, split="devtest")
                print(f"    {lang:>5s} -> [OK]   {flores} ({len(ds)} sentences) [{get_tier(lang)}]")
            except Exception:
                print(f"    {lang:>5s} -> [FAIL] {flores}")
        elif flores and flores in wmt_data:
            print(f"    {lang:>5s} -> [OK]   WMT22 en-{wmt} ({len(wmt_data[flores])} sentences) [{get_tier(lang)}]")
        elif wmt:
            print(f"    {lang:>5s} -> [SKIP] not in WMT22 [{get_tier(lang)}]")
        else:
            print(f"    {lang:>5s} -> [SKIP] no WMT mapping [{get_tier(lang)}]")

    print(f"\n  Dependencies:")
    for pkg, pip_name, required in [
        ("sacrebleu", "sacrebleu", True),
        ("comet", "unbabel-comet", not args.skip_comet),
        ("httpx", "httpx", True),
    ]:
        try:
            __import__(pkg)
            print(f"    {pkg:20s} [OK]")
        except ImportError:
            status = "FAIL" if required else "SKIP"
            print(f"    {pkg:20s} [{status}] pip install {pip_name}")
            if required:
                issues.append(f"Missing required: {pip_name}")

    print(f"\n  Services:")
    try:
        with httpx.Client(base_url=args.nllb_url, timeout=5.0) as client:
            resp = client.get("/health")
            if resp.status_code == 200:
                print(f"    NLLB   [OK]   {args.nllb_url}")
            else:
                print(f"    NLLB   [WARN] {args.nllb_url} (status {resp.status_code})")
    except Exception as e:
        print(f"    NLLB   [SKIP] {args.nllb_url} ({type(e).__name__})")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if args.skip_google:
        print(f"    Google [SKIP] --skip-google")
    elif project:
        print(f"    Google [OK]   project={project}")
    else:
        issues.append("GOOGLE_CLOUD_PROJECT not set")
        print(f"    Google [FAIL] GOOGLE_CLOUD_PROJECT not set")

    print(f"\n{'=' * 60}")
    if issues:
        print(f"  {len(issues)} issue(s):")
        for issue in issues:
            print(f"    - {issue}")
        return 1
    else:
        print("  All checks passed. Ready to benchmark.")
        return 0


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.dry_run:
        return dry_run(args)

    languages = [lang.strip() for lang in args.languages.split(",")]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    Path(args.cache_dir).mkdir(parents=True, exist_ok=True)

    flores_data = load_flores_devtest(languages)
    en_key = "eng_Latn"
    if en_key not in flores_data:
        logger.info("FLORES-200 unavailable, trying WMT22 fallback...")
        flores_data = load_wmt_testset(languages)
    if en_key not in flores_data:
        logger.error("No dataset available. Set HF_TOKEN for FLORES-200, or install sacrebleu for WMT.")
        return 1

    source_sentences = flores_data[en_key]
    if args.samples > 0:
        source_sentences = source_sentences[: args.samples]
    logger.info("Using %d English source sentences", len(source_sentences))

    nllb_client: Optional[httpx.Client] = None
    try:
        nllb_client = httpx.Client(base_url=args.nllb_url, timeout=120.0)
        resp = nllb_client.get("/health")
        if resp.status_code == 200:
            logger.info("NLLB service healthy at %s", args.nllb_url)
        else:
            logger.warning("NLLB health check returned %d", resp.status_code)
    except Exception as e:
        logger.warning("Cannot reach NLLB at %s: %s — running Google-only", args.nllb_url, e)
        nllb_client = None

    results: List[Dict[str, Any]] = []
    for lang in languages:
        flores_code = BCP47_TO_FLORES.get(lang)
        if not flores_code:
            logger.warning("Skipping %s — no FLORES-200 mapping", lang)
            continue

        if flores_code not in flores_data:
            logger.warning("Skipping %s — no reference data loaded", lang)
            continue

        ref_sentences = flores_data[flores_code]
        if args.samples > 0:
            ref_sentences = ref_sentences[: args.samples]

        n = min(len(source_sentences), len(ref_sentences))
        logger.info("Benchmarking en -> %s (%s, %d sentences, tier=%s)", lang, flores_code, n, get_tier(lang))

        pair_result = run_benchmark_for_pair(
            nllb_client=nllb_client,
            target_lang=lang,
            source_sentences=source_sentences[:n],
            reference_sentences=ref_sentences[:n],
            batch_size=args.batch_size,
            skip_google=args.skip_google,
            skip_comet=args.skip_comet,
            cache_dir=args.cache_dir,
        )
        results.append(pair_result)

    if nllb_client:
        nllb_client.close()

    write_report(results, output_dir)
    print_summary(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
