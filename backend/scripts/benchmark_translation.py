#!/usr/bin/env python3
"""Benchmark self-hosted translation models against Google Cloud Translation V3.

Reusable benchmark for comparing any CTranslate2-based NLLB model variant
(600M, 1.3B, 3.3B) against Google Cloud Translation V3. Uses WMT test sets
via sacrebleu (no auth needed) as reference corpus.

Metrics: chrF++ (primary, robust for CJK), BLEU (secondary), COMET (optional).
Results are labeled per model and saved as JSON + CSV for cross-model comparison.

Prerequisites:
    pip install sacrebleu httpx google-cloud-translate

Usage:
    # Dry run — validate dataset loading and dependencies
    python3 scripts/benchmark_translation.py --dry-run

    # Benchmark a specific model (label it for comparison)
    python3 scripts/benchmark_translation.py \
        --nllb-url http://localhost:10150 \
        --model-name nllb-200-distilled-600M \
        --output-dir /tmp/benchmark-results \
        --skip-comet

    # Compare multiple models (Google results cached, no re-billing)
    for model in 600M 1.3B 3.3B; do
        python3 scripts/benchmark_translation.py \
            --nllb-url http://localhost:10150 \
            --model-name "nllb-200-$model" \
            --output-dir /tmp/benchmark-results \
            --skip-comet
    done

    # NLLB-only (skip Google, useful for quick iteration)
    python3 scripts/benchmark_translation.py \
        --nllb-url http://localhost:10150 --skip-google

    # Specific languages only
    python3 scripts/benchmark_translation.py \
        --nllb-url http://localhost:10150 --languages de,zh,ja,ru,uk
"""

import argparse
import csv
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

# Best WMT test set for each en->X pair. sacrebleu downloads on demand, no auth.
WMT_LANGPAIR_MAP: Dict[str, Tuple[str, str]] = {
    "es": ("wmt24", "en-es"),
    "zh": ("wmt24", "en-zh"),
    "hi": ("wmt24", "en-hi"),
    "ru": ("wmt24", "en-ru"),
    "ja": ("wmt24", "en-ja"),
    "de": ("wmt24", "en-de"),
    "uk": ("wmt24", "en-uk"),
}


def detect_model_name(nllb_url: str) -> str:
    """Try to detect model name from NLLB service /health endpoint."""
    try:
        with httpx.Client(base_url=nllb_url, timeout=5.0) as client:
            resp = client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                model_dir = data.get("model_dir", "")
                if model_dir:
                    return model_dir.rstrip("/").split("/")[-1]
                return data.get("model", data.get("model_name", "unknown"))
    except Exception:
        pass
    return "unknown"


def get_tier(lang: str) -> str:
    for tier, langs in LANG_TIERS.items():
        if lang in langs:
            return tier
    return "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark NLLB vs Google Cloud Translation using WMT test sets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--nllb-url", type=str, default="http://localhost:8080", help="Base URL of NLLB service")
    parser.add_argument(
        "--model-name",
        type=str,
        default="",
        help="Model name for labeling results (e.g. nllb-200-distilled-600M). Auto-detected from service if empty.",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default=",".join(ALL_TARGET_LANGUAGES),
        help="Comma-separated BCP-47 target language codes",
    )
    parser.add_argument("--output-dir", type=str, default="/tmp/benchmark-results", help="Output directory for results")
    parser.add_argument("--samples", type=int, default=0, help="Max sentences per pair (0 = all, ~1000)")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without running translations")
    parser.add_argument("--skip-google", action="store_true", help="Skip Google Translate")
    parser.add_argument("--skip-comet", action="store_true", help="Skip COMET metric (requires GPU)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for NLLB API calls")
    parser.add_argument(
        "--cache-dir", type=str, default="/tmp/benchmark-translation-cache", help="Cache dir for Google responses"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def load_wmt_data(target_lang: str, max_samples: int = 0) -> Optional[Tuple[List[str], List[str]]]:
    """Load source/reference sentence pairs from WMT test sets via sacrebleu.

    Returns (source_sentences, reference_sentences) or None if unavailable.
    No authentication required — sacrebleu downloads data on demand.
    """
    try:
        import sacrebleu
    except ImportError:
        logger.error("sacrebleu not installed: pip install sacrebleu")
        return None

    if target_lang not in WMT_LANGPAIR_MAP:
        return None

    test_set, langpair = WMT_LANGPAIR_MAP[target_lang]
    try:
        src_path = sacrebleu.get_source_file(test_set, langpair)
        ref_paths = sacrebleu.get_reference_files(test_set, langpair)
    except Exception as e:
        logger.warning("Cannot load WMT %s %s: %s", test_set, langpair, e)
        return None

    with open(src_path, 'r', encoding='utf-8') as f:
        sources = [line.strip() for line in f if line.strip()]
    with open(ref_paths[0], 'r', encoding='utf-8') as f:
        refs = [line.strip() for line in f if line.strip()]

    n = min(len(sources), len(refs))
    if max_samples > 0:
        n = min(n, max_samples)

    return sources[:n], refs[:n]


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
    with open(cache_path / f"google_{target_lang}.json", 'w', encoding='utf-8') as f:
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
    api_batch_size = 32
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
    """Corpus-level BLEU via sacrebleu (13a tokenizer)."""
    try:
        import sacrebleu
    except ImportError:
        return None
    bleu = sacrebleu.corpus_bleu(hypotheses, [references])
    return round(bleu.score, 2)


def compute_chrf_pp(hypotheses: List[str], references: List[str]) -> Optional[float]:
    """Corpus-level chrF++ (character 6-grams + word bigrams)."""
    try:
        import sacrebleu
    except ImportError:
        return None
    chrf = sacrebleu.corpus_chrf(hypotheses, [references], word_order=2)
    return round(chrf.score, 2)


def compute_comet(sources: List[str], hypotheses: List[str], references: List[str]) -> Optional[float]:
    """COMET score using wmt22-comet-da (best human-judgment correlation)."""
    try:
        from comet import download_model, load_from_checkpoint
    except ImportError:
        logger.info("COMET skipped (pip install unbabel-comet)")
        return None

    try:
        import torch

        gpus = 1 if torch.cuda.is_available() else 0
    except ImportError:
        gpus = 0

    model_path = download_model("Unbabel/wmt22-comet-da")
    model = load_from_checkpoint(model_path)
    data = [{"src": s, "mt": h, "ref": r} for s, h, r in zip(sources, hypotheses, references)]
    output = model.predict(data, batch_size=32, gpus=gpus)
    score = output.system_score if hasattr(output, 'system_score') else output[1]
    return round(float(score), 4)


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
        total_chars = sum(len(s) for s in sources)
        result["nllb"]["chars_per_second"] = round(total_chars / max(total_latency, 0.001))

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


def write_report(results: List[Dict[str, Any]], output_dir: Path, model_name: str = "unknown") -> None:
    """Write JSON report (without raw translations) and CSV summary."""
    report_slim = []
    for r in results:
        entry = {
            "target_lang": r["target_lang"],
            "tier": r["tier"],
            "dataset": r.get("dataset", ""),
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

    report_name = model_name.replace("/", "_").replace(" ", "_")
    json_path = output_dir / f"benchmark_{report_name}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(
            {
                "benchmark": "nllb-vs-google-wmt",
                "model": model_name,
                "source": "en",
                "results": report_slim,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("JSON report: %s", json_path)

    csv_path = output_dir / f"benchmark_{report_name}.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "target_lang",
                "tier",
                "dataset",
                "num_sentences",
                "nllb_bleu",
                "nllb_chrf_pp",
                "nllb_comet",
                "nllb_latency_s",
                "google_bleu",
                "google_chrf_pp",
                "google_comet",
                "google_latency_s",
                "bleu_delta",
                "chrf_pp_delta",
            ]
        )
        for r in report_slim:
            nm = r["nllb"]["metrics"]
            gm = r["google"]["metrics"]
            nb = nm.get("bleu")
            gb = gm.get("bleu")
            nc = nm.get("chrf_pp")
            gc = gm.get("chrf_pp")
            writer.writerow(
                [
                    r["target_lang"],
                    r["tier"],
                    r.get("dataset", ""),
                    r["num_sentences"],
                    nb,
                    nc,
                    nm.get("comet"),
                    r["nllb"]["latency_seconds"],
                    gb,
                    gc,
                    gm.get("comet"),
                    r["google"]["latency_seconds"],
                    round(nb - gb, 2) if nb is not None and gb is not None else None,
                    round(nc - gc, 2) if nc is not None and gc is not None else None,
                ]
            )
    logger.info("CSV summary: %s", csv_path)


def _fmt(v: Optional[float], w: int = 7) -> str:
    if v is not None:
        return f"{v:{w}.1f}"
    return f"{'--':>{w}}"


def _fmt4(v: Optional[float], w: int = 8) -> str:
    if v is not None:
        return f"{v:{w}.4f}"
    return f"{'--':>{w}}"


def print_summary(results: List[Dict[str, Any]], model_name: str = "unknown") -> None:
    """Print formatted summary table grouped by tier."""
    header = (
        f"{'Lang':>6s} {'Tier':>6s} {'Data':>5s}  "
        f"{'NLLB BLEU':>9s} {'G BLEU':>7s} {'d':>6s}  "
        f"{'NLLB chrF++':>11s} {'G chrF++':>8s} {'d':>6s}  "
        f"{'NLLB COMET':>10s} {'G COMET':>8s}"
    )
    sep = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print(f"BENCHMARK: {model_name} vs Google Cloud Translation V3")
    print("Corpus: WMT test sets (sacrebleu) | Source: English")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)

    for tier in ["high", "medium", "low", "unknown"]:
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
            dataset_short = r.get("dataset", "")[:5]

            print(
                f"{r['target_lang']:>6s} {tier:>6s} {dataset_short:>5s}  "
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
            print(f"  {'avg':>4s} {tier:>6s}        {avg_n:9.1f} {avg_g:7.1f} {avg_n - avg_g:+6.1f}  ({pct:+.0f}%)")
        print(sep)

    all_nbleu = [r["nllb"]["metrics"]["bleu"] for r in results if r["nllb"]["metrics"].get("bleu") is not None]
    all_gbleu = [r["google"]["metrics"]["bleu"] for r in results if r["google"]["metrics"].get("bleu") is not None]
    if all_nbleu and all_gbleu:
        avg_n = sum(all_nbleu) / len(all_nbleu)
        avg_g = sum(all_gbleu) / len(all_gbleu)
        pct = ((avg_n - avg_g) / avg_g * 100) if avg_g else 0
        print(f"  {'OVERALL AVG':>17s}  {avg_n:9.1f} {avg_g:7.1f} {avg_n - avg_g:+6.1f}  ({pct:+.0f}%)")
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
    ok_count = 0

    print("  WMT datasets (via sacrebleu, no auth needed):")
    try:
        import sacrebleu  # noqa: F401

        for lang in languages:
            if lang in WMT_LANGPAIR_MAP:
                data = load_wmt_data(lang, max_samples=args.samples)
                if data:
                    src, _ref = data
                    ts, lp = WMT_LANGPAIR_MAP[lang]
                    print(f"    {lang:>5s} -> [OK]   {ts} {lp} ({len(src)} sentences) [{get_tier(lang)}]")
                    ok_count += 1
                else:
                    ts, lp = WMT_LANGPAIR_MAP[lang]
                    print(f"    {lang:>5s} -> [FAIL] {ts} {lp}")
                    issues.append(f"Cannot load WMT for {lang}")
            else:
                print(f"    {lang:>5s} -> [SKIP] No WMT test set available")
    except ImportError:
        issues.append("sacrebleu not installed")
        print("    [FAIL] sacrebleu not installed")

    print(f"\n  Dependencies:")
    for pkg, pip_name, required in [
        ("sacrebleu", "sacrebleu", True),
        ("comet", "unbabel-comet", not args.skip_comet),
        ("httpx", "httpx", True),
    ]:
        try:
            __import__(pkg)
            print(f"    {pkg:20s} [OK]")
            ok_count += 1
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
                ok_count += 1
            else:
                print(f"    NLLB   [WARN] {args.nllb_url} (status {resp.status_code})")
    except Exception as e:
        print(f"    NLLB   [SKIP] {args.nllb_url} ({type(e).__name__})")

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if args.skip_google:
        print("    Google [SKIP] --skip-google")
    elif project:
        print(f"    Google [OK]   project={project}")
        ok_count += 1
    else:
        print("    Google [WARN] GOOGLE_CLOUD_PROJECT not set")

    print(f"\n{'=' * 60}")
    if issues:
        print(f"  {len(issues)} issue(s):")
        for issue in issues:
            print(f"    - {issue}")
        return 1
    else:
        wmt_langs = [la for la in languages if la in WMT_LANGPAIR_MAP]
        skip_langs = [la for la in languages if la not in WMT_LANGPAIR_MAP]
        print(f"  Ready to benchmark {len(wmt_langs)} language pairs: {', '.join(wmt_langs)}")
        if skip_langs:
            print(f"  Skipped (no WMT data): {', '.join(skip_langs)}")
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

    model_name = args.model_name
    if not model_name:
        model_name = detect_model_name(args.nllb_url)
        if model_name == "unknown":
            model_name = "nllb-200-distilled-600M"
        logger.info("Model: %s (auto-detected)", model_name)
    else:
        logger.info("Model: %s", model_name)

    nllb_client: Optional[httpx.Client] = None
    try:
        nllb_client = httpx.Client(base_url=args.nllb_url, timeout=120.0)
        resp = nllb_client.get("/health")
        if resp.status_code == 200:
            logger.info("NLLB service healthy at %s", args.nllb_url)
        else:
            logger.warning("NLLB health check returned %d", resp.status_code)
    except Exception as e:
        logger.warning("Cannot reach NLLB at %s: %s — will run Google-only if available", args.nllb_url, e)
        nllb_client = None

    results: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for lang in languages:
        data = load_wmt_data(lang, max_samples=args.samples)
        if not data:
            skipped.append(lang)
            continue

        source_sentences, ref_sentences = data
        test_set = WMT_LANGPAIR_MAP[lang][0]
        logger.info(
            "Benchmarking en -> %s (%s, %d sentences, tier=%s)",
            lang,
            test_set,
            len(source_sentences),
            get_tier(lang),
        )

        pair_result = run_benchmark_for_pair(
            nllb_client=nllb_client,
            target_lang=lang,
            source_sentences=source_sentences,
            reference_sentences=ref_sentences,
            batch_size=args.batch_size,
            skip_google=args.skip_google,
            skip_comet=args.skip_comet,
            cache_dir=args.cache_dir,
        )
        pair_result["dataset"] = test_set
        results.append(pair_result)

    if nllb_client:
        nllb_client.close()

    if skipped:
        logger.info("Skipped %d languages (no WMT data): %s", len(skipped), ", ".join(skipped))

    if results:
        write_report(results, output_dir, model_name)
        print_summary(results, model_name)
    else:
        logger.error("No language pairs could be benchmarked")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
