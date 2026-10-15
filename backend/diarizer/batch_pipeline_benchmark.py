"""Public-audio-only ASR batching/chunking qualification, no storage or vendors.

Run from backend with PYTHONPATH=. on an isolated dev GPU. Supply a canonical
AMI WAV and its reference text; results contain counts, WER and hashes only.
This measures the words stage, not VAD/pyannote/storage or end-to-end throughput.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

try:
    import torch  # type: ignore[reportMissingImports]  # GPU runtime only
    import nemo.collections.asr as nemo_asr  # type: ignore[reportMissingImports]  # GPU runtime only
except ImportError:
    torch = None
    nemo_asr = None

from config.batch_pipeline_providers import ProviderConfig
from diarizer.batch_pipeline import pack_windows, speech_windows
from diarizer.batch_pipeline_models import ParakeetWords, decode_pcm16_wav, pin_parakeet_decoding
from utils.batch_pipeline.contracts import Priority, WorkItem


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def edit_distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        following = [i]
        for j, right in enumerate(hypothesis, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (left != right)))
        row = following
    return row[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--vad-json', help='Optional public-audio VAD spans [[start,end],...]')
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', default='nvidia/parakeet-tdt-0.6b-v3')
    args = parser.parse_args()
    if torch is None or nemo_asr is None:
        raise RuntimeError('benchmark requires the GPU runtime with torch and NeMo')

    body = Path(args.audio).read_bytes()
    samples = decode_pcm16_wav(body)
    duration = len(samples) / 16000
    reference = tokens(Path(args.reference).read_text())
    if not reference:
        raise ValueError('public reference must contain words')
    raw_spans = json.loads(Path(args.vad_json).read_text()) if args.vad_json else [(0, duration)]
    spans = [(s['start'], s['end']) if isinstance(s, dict) else tuple(s) for s in raw_spans]
    model = nemo_asr.models.ASRModel.from_pretrained(args.model).cuda().eval()
    pin_parakeet_decoding(model)
    provider = ParakeetWords(model, enforce_eager=True)
    rows = []
    report = {
        'audio_sha256': hashlib.sha256(body).hexdigest(),
        'audio_seconds': duration,
        'reference_sha256': hashlib.sha256(Path(args.reference).read_bytes()).hexdigest(),
        'reference_tokens': len(reference),
        'device': torch.cuda.get_device_name(),
        'torch': torch.__version__,
        'model': args.model,
        'cuda_graph_policy': 'persistently_disabled_and_asserted',
        'rows': rows,
        'scope': 'ASR only; whole conversation input, internal windows; no persistence',
    }
    item = WorkItem('public-ami', 'synthetic-benchmark', 0, 'public-local://ami', duration, Priority.DEEP)
    for attention in ['local', 'full']:
        (
            model.change_attention_model('rel_pos_local_attn', [256, 256])
            if attention == 'local'
            else model.change_attention_model('rel_pos')
        )
        model.change_subsampling_conv_chunking_factor(1)
        provider.transcribe_batch([samples[: min(len(samples), 30 * 16000)]])
        # Full attention on long audio is intentionally bounded; test windows instead.
        modes = ['windows'] if attention == 'full' and duration > 300 else ['whole', 'windows']
        for mode in modes:
            for size in ([1] if mode == 'whole' else [1, 8, 32]):
                for context in ([0] if mode == 'whole' else [0, 2]):
                    config = ProviderConfig(batch_size=size, max_padded_seconds=34 * size, context_seconds=context)
                    windows = list(speech_windows(item, samples, spans, config))
                    batches = (
                        [[samples]]
                        if mode == 'whole'
                        else [[w.samples for w in b] for b in pack_windows(windows, config)]
                    )
                    row: dict[str, Any] = {
                        'attention': attention,
                        'mode': mode,
                        'batch_size': size,
                        'context_seconds': context,
                        'config': asdict(config),
                    }
                    try:
                        words = []
                        ordered = None if mode == 'whole' else list(pack_windows(windows, config))
                        torch.cuda.synchronize()
                        torch.cuda.reset_peak_memory_stats()
                        started = time.perf_counter()
                        with torch.inference_mode():
                            for index, batch in enumerate(batches):
                                result = provider.transcribe_batch(batch)
                                if len(result) != len(batch):
                                    raise ValueError('result cardinality mismatch')
                                for offset, hypothesis in enumerate(result):
                                    if mode == 'whole':
                                        words.extend(hypothesis)
                                        continue
                                    if ordered is None:
                                        raise ValueError('missing window ownership map')
                                    window = ordered[index][offset]
                                    for word in hypothesis:
                                        left, right = [v + window.start for v in word['timestamp']]
                                        if window.core_start <= (left + right) / 2 < window.core_end:
                                            words.append({**word, 'timestamp': [left, right]})
                        torch.cuda.synchronize()
                        elapsed = time.perf_counter() - started
                        hypothesis = tokens(' '.join(w['word'] for w in sorted(words, key=lambda w: w['timestamp'][0])))
                        row.update(
                            status='ok',
                            wall_seconds=elapsed,
                            rtf=elapsed / duration,
                            audio_hours_per_gpu_hour=duration / elapsed,
                            tokens=len(hypothesis),
                            token_deficit_vs_reference=1 - len(hypothesis) / len(reference),
                            wer=edit_distance(reference, hypothesis) / len(reference),
                            peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                            effective_batch_sizes=[len(b) for b in batches],
                        )
                    except Exception as exc:
                        row.update(status='error', exception_type=type(exc).__name__)
                    rows.append(row)
                    Path(args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
