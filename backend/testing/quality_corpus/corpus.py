#!/usr/bin/env python3
"""F6 parity corpus: fetch by checksum, build units, run the batch chain, score.

    corpus.py fetch    --cache DIR [--pin]      download sources; verify (or record) sha256
    corpus.py build    --cache DIR --out DIR    16 kHz PCM16 units + reference JSON
    corpus.py baseline --units DIR --out DIR    production batch chain on every unit (GPU)
    corpus.py score    --units DIR --batch DIR [--legacy DIR] [--baseline-accuracy X] --output scores.json

Public audio only. The cache and the built units live outside Git
(``QUALITY_CORPUS_CACHE``, default ``/Volumes/Ephemeral/quality-corpus``).
``score`` writes the aggregate input for parity rows 1 and 2; it never
writes transcript text.

Pipeline output format (``--batch``/``--legacy`` dirs, one ``<unit>.json`` each)::

    {"words": [{"text": "hello", "start": 1.2, "end": 1.5, "speaker": "SPEAKER_01"}, ...]}

Legacy outputs come from the staging replay of the corpus units through the
legacy path (lane 4's replay driver at batch percent 0); batch outputs from
the same replay at 100%, or from ``baseline`` for main's code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'manifest.json'
LOCK = HERE / 'manifest.lock.json'
DEFAULT_CACHE = Path(os.environ.get('QUALITY_CORPUS_CACHE', '/Volumes/Ephemeral/quality-corpus'))


class CorpusError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def source_urls(manifest: dict) -> dict[str, str]:
    """Every downloadable URL, keyed by a stable cache name."""
    sources, urls = manifest['sources'], {}
    ami = next(g for g in manifest['groups'] if g['id'] == 'ami')
    for meeting in ami['meetings']:
        urls[f'ami_audio/{meeting}.wav'] = sources['ami_audio']['url_template'].format(meeting=meeting)
    for key in ('ami_words', 'librispeech_test_clean', 'voxconverse_test_wav', 'voxconverse_rttm'):
        url = sources[key]['url']
        urls[f'{key}/{url.rsplit("/", 1)[-1]}'] = url
    return urls


def fetch(cache: Path, pin: bool, opener=urllib.request.urlopen) -> dict:
    manifest = json.loads(MANIFEST.read_text())
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {'schema_version': 1, 'sha256': {}}
    for name, url in source_urls(manifest).items():
        target = cache / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            partial = target.with_suffix(target.suffix + '.partial')
            with opener(url, timeout=600) as response, partial.open('wb') as handle:
                shutil.copyfileobj(response, handle, 1 << 20)
            partial.rename(target)
        digest = sha256_file(target)
        expected = lock['sha256'].get(name)
        if expected is None:
            if not pin:
                raise CorpusError(f'unpinned source {name}; run fetch --pin once and commit manifest.lock.json')
            lock['sha256'][name] = digest
        elif expected != digest:
            raise CorpusError(f'checksum mismatch for {name}')
    if pin:
        LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + '\n')
    return lock


def _zip_member(path: Path, member: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(member)


def build(cache: Path, out: Path) -> dict:
    import numpy as np

    from testing.quality_corpus.audio import (
        SAMPLE_RATE,
        crop_turns,
        crop_words,
        load_audio,
        parse_ami_words,
        parse_rttm,
        quiet_bed,
    )
    from testing.quality_corpus.chain import wav_bytes

    manifest = json.loads(MANIFEST.read_text())
    groups = {g['id']: g for g in manifest['groups']}
    (out / 'units').mkdir(parents=True, exist_ok=True)
    (out / 'refs').mkdir(parents=True, exist_ok=True)
    index = {}

    def emit(unit_id, samples, ref):
        (out / 'units' / f'{unit_id}.wav').write_bytes(wav_bytes(samples))
        (out / 'refs' / f'{unit_id}.json').write_text(json.dumps(ref))
        index[unit_id] = {'use': ref['use'], 'seconds': round(len(samples) / SAMPLE_RATE, 3)}

    ami = groups['ami']
    words_zip = cache / 'ami_words' / manifest['sources']['ami_words']['url'].rsplit('/', 1)[-1]
    start, end = ami['crop_seconds']
    for meeting in ami['meetings']:
        audio = load_audio(cache / 'ami_audio' / f'{meeting}.wav')
        xml = {}
        for speaker in ami['speakers']:
            member = manifest['sources']['ami_words']['member_template'].format(meeting=meeting, speaker=speaker)
            try:
                xml[speaker] = _zip_member(words_zip, member).decode()
            except KeyError:
                continue
        words = crop_words(parse_ami_words(xml), start, end)
        emit(
            f'ami-{meeting}',
            audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)],
            {'use': ami['use'], 'text': ' '.join(w['text'] for w in words), 'words': words},
        )

    libri = groups['librispeech']
    tar_path = cache / 'librispeech_test_clean' / 'test-clean.tar.gz'
    with tarfile.open(tar_path) as archive:
        members = {m.name: m for m in archive.getmembers() if m.isfile()}
        chapters = sorted({name.rsplit('/', 1)[0] for name in members if name.endswith('.trans.txt')})
        total = 0.0
        for chapter in chapters:
            if total >= libri['max_seconds']:
                break
            trans = next(n for n in members if n.startswith(chapter + '/') and n.endswith('.trans.txt'))
            lines = archive.extractfile(members[trans]).read().decode().splitlines()  # type: ignore[union-attr]
            pieces, texts = [], []
            pause = np.zeros(int(libri['join_pause_seconds'] * SAMPLE_RATE), dtype=np.float32)
            for line in lines:
                utt, _, text = line.partition(' ')
                flac = f'{chapter}/{utt}.flac'
                body = archive.extractfile(members[flac]).read()  # type: ignore[union-attr]
                tmp = out / '.tmp.flac'
                tmp.write_bytes(body)
                pieces += [load_audio(tmp), pause]
                texts.append(text)
            samples = np.concatenate(pieces)
            total += len(samples) / SAMPLE_RATE
            emit(
                'libri-' + chapter.rsplit('/', 2)[-2] + '-' + chapter.rsplit('/', 1)[-1],
                samples,
                {'use': libri['use'], 'text': ' '.join(texts)},
            )
        (out / '.tmp.flac').unlink(missing_ok=True)

    vox = groups['voxconverse']
    wav_zip = cache / 'voxconverse_test_wav' / 'voxconverse_test_wav.zip'
    rttm_zip = cache / 'voxconverse_rttm' / 'master.zip'
    start, end = vox['crop_seconds']
    with zipfile.ZipFile(wav_zip) as archive:
        wavs = sorted(n for n in archive.namelist() if n.endswith('.wav'))[: vox['files']]
        for name in wavs:
            file_id = Path(name).stem
            tmp = out / '.tmp.wav'
            tmp.write_bytes(archive.read(name))
            audio = load_audio(tmp)
            rttm = _zip_member(
                rttm_zip, manifest['sources']['voxconverse_rttm']['member_template'].format(file_id=file_id)
            ).decode()
            turns = crop_turns(parse_rttm(rttm), start, end)
            emit(
                f'vox-{file_id}',
                audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)],
                {'use': vox['use'], 'turns': [t.__dict__ for t in turns]},
            )
        (out / '.tmp.wav').unlink(missing_ok=True)

    silence = groups['silence']
    for i in range(silence['clips']):
        emit(f'silence-{i:02d}', quiet_bed(silence['seconds'], silence['seed'] + i), {'use': silence['use']})
    (out / 'index.json').write_text(json.dumps(index, indent=1, sort_keys=True))
    return index


def score(
    units_dir: Path, batch_dir: Path, legacy_dir: Path | None, baseline_accuracy: float | None, pinned: bool
) -> dict:
    """Aggregate parity input for rows 1 and 2 (no text leaves this function)."""
    from scripts.parity.scorers import pooled_wer, speaker_accuracy, words_text
    from testing.quality_corpus.audio import Turn, speaker_at, turns_from_words

    index = json.loads((units_dir / 'index.json').read_text())
    pipelines = {'batch': batch_dir} | ({'legacy': legacy_dir} if legacy_dir else {})
    result: dict = {'schema_version': 1, 'pinned': pinned, 'pipelines': {}}
    wer_seconds = sum(v['seconds'] for v in index.values() if 'wer' in v['use'])
    result['corpus_minutes'] = round(wer_seconds / 60.0, 2)
    for name, directory in pipelines.items():
        wer_pairs, speaker_words, speaker_correct, silence_words, missing = [], 0, 0, 0, 0
        scored_seconds, silence_tokens = 0.0, 0
        for unit_id, meta in sorted(index.items()):
            ref = json.loads((units_dir / 'refs' / f'{unit_id}.json').read_text())
            path = directory / f'{unit_id}.json'
            if not path.exists():
                missing += 1
                continue
            words = json.loads(path.read_text()).get('words') or []
            if 'wer' in meta['use']:
                wer_pairs.append((ref['text'], words_text(words)))
                scored_seconds += meta['seconds']
            if 'silence' in meta['use']:
                silence_words += len(words)
                # Every token emitted on a silence bed is an insertion error in the pooled WER, fillers
                # included (normalization would drop them), so row 1's delta charges hallucinations.
                silence_tokens += len(words_text(words).split())
            if 'speaker' in meta['use']:
                turns = (
                    [Turn(**t) for t in ref['turns']] if 'turns' in ref else turns_from_words(ref.get('words') or [])
                )
                truth = [
                    {'start': w['start'], 'end': w['end'], 'speaker': speaker_at(turns, (w['start'] + w['end']) / 2)}
                    for w in words
                ]
                scored = speaker_accuracy(truth, [w.get('speaker') for w in words])
                speaker_words += scored['words']
                speaker_correct += scored['correct_1to1']
        wer = pooled_wer(wer_pairs)
        wer['errors'] += silence_tokens
        wer['wer'] = wer['errors'] / wer['reference_words'] if wer['reference_words'] else None
        result['pipelines'][name] = {
            'wer': wer,
            'speaker': {
                'words': speaker_words,
                'correct_1to1': speaker_correct,
                'accuracy_1to1': speaker_correct / speaker_words if speaker_words else None,
            },
            'silence_inserted_words': silence_words,
            'missing_units': missing,
            'scored_wer_minutes': round(scored_seconds / 60.0, 2),
        }
    if baseline_accuracy is not None:
        result['baseline'] = {'speaker_accuracy': baseline_accuracy}
    return result


def baseline(units_dir: Path, out: Path) -> dict:
    """Main's code: the production batch chain on every unit; writes per-unit word outputs (public text)."""
    from testing.quality_corpus.chain import labelled_words, run_chain

    units = {p.stem: p.read_bytes() for p in sorted((units_dir / 'units').glob('*.wav'))}
    run = run_chain(units, {})
    out.mkdir(parents=True, exist_ok=True)
    for unit_id, payload in run['payloads'].items():
        (out / f'{unit_id}.json').write_text(json.dumps({'words': labelled_words(payload)}))
    return {'units': len(units), 'outputs': len(run['payloads']), 'counts': run['counts']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='F6 parity corpus.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fetch')
    p.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    p.add_argument('--pin', action='store_true')
    p = sub.add_parser('build')
    p.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('baseline')
    p.add_argument('--units', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('score')
    p.add_argument('--units', type=Path, required=True)
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--legacy', type=Path)
    p.add_argument('--baseline-accuracy', type=float)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'fetch':
            lock = fetch(args.cache, args.pin)
            print(json.dumps({'pinned_sources': len(lock['sha256'])}))
        elif args.command == 'build':
            print(json.dumps({'units': len(build(args.cache, args.out))}))
        elif args.command == 'baseline':
            print(json.dumps(baseline(args.units, args.out)))
        else:
            scores = score(args.units, args.batch, args.legacy, args.baseline_accuracy, LOCK.exists())
            args.output.write_text(json.dumps(scores, indent=1, sort_keys=True) + '\n')
            print(json.dumps({k: v for k, v in scores.items() if k != 'pipelines'}))
    except CorpusError as error:
        print(f'CORPUS_ERROR {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
