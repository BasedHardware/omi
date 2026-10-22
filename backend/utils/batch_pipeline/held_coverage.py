"""Held WAV admission keeps exact source coordinates through canonical packing."""

from pathlib import Path
from tempfile import TemporaryDirectory
import wave

from config import refactor_modes
from utils.batch_pipeline.audio import RATE, audio_unit
from utils.batch_pipeline.capture_decode import UNIT_FRAMES, canonical_pcm
from utils.capture import coverage
from utils.capture.batch_coverage import piece_runs, provenance_unit
from utils.sync.held_coverage import proof, observe


class HeldDecoder:
    def __init__(self, uid, path, capture_at, meta, *, legacy):
        self.uid, self.path, self.capture_at, self.meta = uid, path, capture_at, meta
        self.legacy = legacy
        self.all_covered = False

    def __call__(self, max_seconds):
        if not refactor_modes.shadow_or_serve(coverage.FLAG):
            yield from self.legacy(self.path, self.capture_at, max_seconds)
            return
        decision = proof(self.uid, self.path, {**self.meta, '_batch_coverage': True})
        if decision is None:
            yield from self.legacy(self.path, self.capture_at, max_seconds)
            return
        if not refactor_modes.serving_for(coverage.FLAG, self.uid):
            observe(decision, 'batch', 'would_skip')
            yield from self.legacy(self.path, self.capture_at, max_seconds)
            return
        if decision.state == 'covered':
            observe(decision, 'batch', 'skipped')
            self.all_covered = True
            return
        unit_samples = min(UNIT_FRAMES, int(max_seconds * RATE))
        if unit_samples < 1 or max_seconds > 7200:
            raise ValueError('invalid dedicated capture-unit ceiling')
        if decision.mapping['claim']['rate_hz'] != RATE:
            # Trim in the proven native clock, then resample each kept interval.
            # Resampled words carry no inferred source-frame receipt.
            yield from native_units(self.path, self.capture_at, decision, unit_samples)
            observe(decision, 'batch', 'skipped')
            return
        pcm = canonical_pcm(self.path)
        if len(pcm) != decision.sample_count * 2:
            raise ValueError('held source geometry changed during admission')
        observe(decision, 'batch', 'skipped')
        for low, high in decision.uncovered:
            for start in range(low, high, unit_samples):
                end = min(start + unit_samples, high)
                relative = start - decision.sample_start
                unit = audio_unit(
                    self.capture_at + relative / RATE, pcm[relative * 2 : (end - decision.sample_start) * 2]
                )
                runs = piece_runs(decision.mapping, start, end - start, 0, self.meta)
                yield provenance_unit(unit, runs)


def native_units(path, capture_at, decision, unit_samples):
    rate = decision.mapping['claim']['rate_hz']
    with TemporaryDirectory(dir=Path(path).parent) as directory, wave.open(path, 'rb') as source:
        temporary = str(Path(directory) / 'uncovered.wav')
        for low, high in decision.uncovered:
            relative = low - decision.sample_start
            source.setpos(relative)
            payload = source.readframes(high - low)
            if len(payload) != (high - low) * 2:
                raise ValueError('held native source slice truncated')
            with wave.open(temporary, 'wb') as output:
                output.setparams(source.getparams())
                output.writeframes(payload)
            pcm = canonical_pcm(temporary)
            if not pcm:
                raise ValueError('empty held native slice')
            for offset in range(0, len(pcm), unit_samples * 2):
                yield audio_unit(
                    capture_at + relative / rate + offset / (2 * RATE), pcm[offset : offset + unit_samples * 2]
                )
