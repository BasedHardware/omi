"""Audio-file recordings: from a WAV file to the scripted lines the scenario events already write.

Two steps, because they run in different environments:

1. :func:`prepare`, before the lab environment (which clears the process env and refuses the network):
   load the file as canonical 16 kHz mono PCM16, find its STT cassette, and on a miss act on ``--stt``:

   - ``replay`` (default): fail with :class:`AudioError` naming the missing key and the command that
     would record it. No network, no model.
   - ``record-vendor``: the ``record-stt`` path (``cassette.adapters.make_adapter('prerecorded')``,
     ``cassette.recorder.Recorder``, the persistent ``ledger.SpendLedger`` under
     ``$ROOT/stt_records/scenario-<name>/`` with ``--stt-budget-usd`` as its cap). Needs vendor
     credentials and an ``stt`` provider + model pin in the scenario.
   - ``record-local``: the registered local model (``cassette/local.py``), free, on this machine.

   ``replay`` looks in the committed fixtures (``scenario/fixtures/stt_cassette/``, which must be
   ``synthetic``: real transcripts never go in git) and the lab root's cassette cache. With a provider +
   model pin it takes that exact key; without one, every cassette of this audio (same language and
   vocabulary), best source first: vendor, then local, then synthetic, newest first within a source.
   A record mode looks up its own recorder's key in the lab root (``Recorder.ensure``) and records only
   when that is missing, so ``record-local`` adds a local cassette beside a committed synthetic one.

2. :func:`materialize`, inside the lab environment: run the words through the lab's existing lane code,
   so the product calls between "audio" and "segments" are the same ones a day replay runs:

   - batch recordings: ``lanes.batch.replay_record_lane`` (production ``decode_pcm16_wav``, the real
     ``PipelineWorker.process_batch`` with local Silero VAD, windows, packing and validation, then the
     real ``projection_segments``);
   - sync fragments: ``lanes.sync.replay_sync_lane`` (the real ``retrieve_vad_segments`` over local
     Silero, ``postprocess_words``, ``first_word_offset``).

   The segments become the recording's ``lines``; from there the scenario's transcript landing, fast
   finish and sync events write them through the same product calls scripted lines use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import shlex
from typing import Any, Callable, Optional, Sequence

from testing.pipeline_lab.cassette.format import SOURCES, Cassette, CassetteKey, audio_sha256, recorded_for_audio

STT_MODES = ('replay', 'record-vendor', 'record-local')
DEFAULT_STT_MODE = 'replay'
FIXTURE_CASSETTES = Path(__file__).resolve().parent / 'fixtures' / 'stt_cassette'
SOURCE_PREFERENCE = ('vendor', 'local', 'synthetic')  # closest to production first
COMMAND = 'python -m testing.pipeline_lab scenario run'


class AudioError(RuntimeError):
    """An audio recording cannot get its words; the message is the scenario's error (no transcript text)."""


@dataclass
class PreparedAudio:
    label: str
    pcm16: bytes
    cassette: Cassette
    origin: str  # fixture | lab_root | recorded
    mode: str
    route: Optional[dict[str, Any]] = None  # stt_routing: the engine production would pick, when routing is on

    def summary(self) -> dict[str, Any]:
        c = self.cassette
        return {
            'source': c.source,
            # Provenance (fixture | lab_root | recorded): kept for inspection, not compared across repeats
            # (determinism.SCENARIO_ARTIFACTS), since a record-mode repeat replays what its first run recorded.
            'cassette_origin': self.origin,
            'provider': c.key.provider,
            'model': c.key.model,
            'language': c.key.language,
            'adapter': c.adapter,
            'cassette': c.key.digest[:12],
            'audio_seconds': round(c.audio_seconds, 3),
            'cassette_words': len(c.words),
            'usd': c.usd,
            **({'route': self.route} if self.route is not None else {}),
        }


# ---- lookup ---------------------------------------------------------------------------------------


def _fixture_cassettes(directory: Path) -> list[Cassette]:
    import json

    out = []
    for path in sorted(directory.glob('*/*.json')) if directory.is_dir() else []:
        cassette = Cassette.from_json(json.loads(path.read_text(encoding='utf-8')))
        if cassette.source != 'synthetic':
            raise AudioError(
                f'committed cassette {path.name[:12]} has source {cassette.source!r}; only synthetic cassettes '
                'may be committed (real transcripts never go in git)'
            )
        if path.stem != cassette.key.digest:
            raise AudioError(f'committed cassette {path.name[:12]} is not filed under its key digest')
        out.append(cassette)
    return out


def _matches(cassette: Cassette, key: CassetteKey, pinned: bool) -> bool:
    k = cassette.key
    if pinned:
        return k == key
    return (k.audio_sha256, k.language, k.vocabulary_sha256) == (key.audio_sha256, key.language, key.vocabulary_sha256)


def _best(cassettes: Sequence[Cassette]) -> Optional[Cassette]:
    if not cassettes:
        return None
    rank = {source: i for i, source in enumerate(SOURCE_PREFERENCE)}
    return sorted(cassettes, key=lambda c: (rank.get(c.source, len(SOURCES)), _negated(c.recorded_at)))[0]


def _negated(stamp: str) -> tuple:
    # Newest first within one source: sort on the negated character codes of the ISO stamp.
    return tuple(-ord(ch) for ch in stamp or '')


def _key(pcm16: bytes, stt: dict[str, Any], provider: str, model: str) -> CassetteKey:
    return CassetteKey.for_audio(
        pcm16, provider=provider, model=model, language=stt.get('language'), vocabulary=stt.get('vocabulary') or []
    )


def find(
    pcm16: bytes, stt: dict[str, Any], *, root: Optional[Path], fixtures: Path = FIXTURE_CASSETTES
) -> Optional[tuple[Cassette, str]]:
    pinned = bool(stt.get('provider'))
    key = _key(pcm16, stt, stt.get('provider') or '-', stt.get('model') or '-')
    origin: dict[str, str] = {}
    found = []
    for cassette in _fixture_cassettes(fixtures):
        if _matches(cassette, key, pinned):
            found.append(cassette)
            origin[cassette.key.digest] = 'fixture'
    if root is not None and Path(root).is_dir():
        # Indexed cassettes, else (pinned or not) ones recorded before the by-audio index existed.
        for cassette in recorded_for_audio(key.audio_sha256, root):
            if _matches(cassette, key, pinned) and cassette.key.digest not in origin:
                found.append(cassette)
                origin[cassette.key.digest] = 'lab_root'
        if pinned and not found:
            from testing.pipeline_lab.cassette.format import load

            # A pinned key recorded before the index, while the index lists only other keys of this audio.
            cassette = load(key, root)
            if cassette is not None:
                found.append(cassette)
                origin[cassette.key.digest] = 'lab_root'
    best = _best(found)
    return (best, origin[best.key.digest]) if best is not None else None


# ---- prepare (before the lab environment) ---------------------------------------------------------


def _miss_message(scenario: Any, rec: Any, pcm16: bytes, stt: dict[str, Any]) -> str:
    pin = f', {stt["provider"]}/{stt["model"]}' if stt.get('provider') else ''
    where = shlex.quote(scenario.path or scenario.name)
    head = (
        f'recording {rec.label}: no STT cassette for {Path(rec.audio_file).name} '
        f'(audio {audio_sha256(pcm16)[:12]}, language {stt.get("language") or "multi"}{pin}). '
    )
    vendor = f'`{COMMAND} {where} --stt record-vendor --stt-budget-usd 0.05` (vendor credentials)'
    if stt.get('provider'):
        return head + f'Record it with {vendor}, or drop the stt pin to use any recorded cassette of this file'
    return head + (
        f'Record one with `{COMMAND} {where} --stt record-local` (a local model on this machine, no network), '
        f'or pin stt.provider and stt.model in the scenario and run {vendor}'
    )


def _record_dir(root: Path, scenario_name: str) -> Path:
    from testing.pipeline_lab.store import private_subdir, safe_segment

    return private_subdir(root / 'stt_records' / safe_segment(f'scenario-{scenario_name}', 'record id'))


def _vendor_recorder(scenario: Any, stt: dict[str, Any], root: Path, budget_usd: Optional[float], adapter: Any):
    from testing.pipeline_lab.cassette.adapters import make_adapter
    from testing.pipeline_lab.cassette.recorder import Recorder
    from testing.pipeline_lab.ledger import SpendLedger

    if not stt.get('provider'):
        raise AudioError(
            'record-vendor needs stt.provider and stt.model in the scenario: the prerecorded provider and model '
            'the cassette is filed under (the overlay must serve that pair)'
        )
    if budget_usd is None:
        raise AudioError('record-vendor needs --stt-budget-usd (the hard spend cap for this scenario\'s recording)')
    directory = _record_dir(root, scenario.name)
    adapter = adapter or make_adapter('prerecorded', provider=stt['provider'], model=stt['model'])
    ledger = SpendLedger(directory / 'ledger.json', budget_usd=budget_usd)
    return Recorder(adapter, ledger, vendor_log=directory / 'vendor_log.jsonl', root=root)


def _local_recorder(scenario: Any, stt: dict[str, Any], root: Path, local: Any):
    from testing.pipeline_lab.cassette.local import LocalAdapter, local_recorder
    from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder

    recorder = local or local_recorder()
    if not recorder.installed:
        recorder.recognize(b'', None)  # raises LocalRecorderNotInstalled with the install hint
    if stt.get('provider') and (stt['provider'], stt['model']) != (recorder.provider, recorder.model):
        raise AudioError(
            f'stt pins {stt["provider"]}/{stt["model"]}, but record-local files cassettes under the local model\'s '
            f'own key {recorder.provider}/{recorder.model}; remove the pin, or pin that pair'
        )
    directory = _record_dir(root, scenario.name)
    return Recorder(LocalAdapter(recorder), InMemoryLedger(0.0), vendor_log=directory / 'vendor_log.jsonl', root=root)


def prepare(
    scenario: Any,
    *,
    mode: str = DEFAULT_STT_MODE,
    budget_usd: Optional[float] = None,
    root: Optional[Path] = None,
    fixtures: Path = FIXTURE_CASSETTES,
    local: Any = None,
    vendor_adapter: Any = None,
    env: Optional[dict[str, str]] = None,
) -> dict[str, PreparedAudio]:
    """Every ``audio_file`` recording's PCM and cassette, recording on a miss per ``mode``.

    ``env`` is the scenario env with the arm's on top. With ``OMI_PIPELINE_LAB_STT_ROUTING=product`` in it,
    each recording is routed by production's batch routing (``stt_routing/routing.py``) and plays the
    cassette of the engine chosen, so arms that route differently transcribe differently."""
    from testing.pipeline_lab.cassette.local import LocalRecorderNotInstalled
    from testing.pipeline_lab.lanes.audio import load_pcm16

    if mode not in STT_MODES:
        raise AudioError(f'--stt must be one of {STT_MODES}')
    recordings = scenario.audio_recordings
    if not recordings:
        return {}
    if root is None:
        from testing.pipeline_lab.scenario.paths import scenario_lab_root

        root = scenario_lab_root()
    stt = dict(scenario.stt)
    from testing.pipeline_lab.stt_routing import routing

    env = dict(env or {})
    if routing.enabled(env):
        return _prepare_routed(
            scenario, recordings, env, mode=mode, root=Path(root), fixtures=fixtures, budget_usd=budget_usd
        )
    recorder = None
    out: dict[str, PreparedAudio] = {}
    for rec in recordings:
        pcm16 = load_pcm16(rec.audio_file)
        if mode == 'replay':
            hit = find(pcm16, stt, root=root, fixtures=fixtures)
            if hit is None:
                raise AudioError(_miss_message(scenario, rec, pcm16, stt))
            out[rec.label] = PreparedAudio(rec.label, pcm16, hit[0], hit[1], mode)
            continue
        if recorder is None:
            from testing.pipeline_lab.store import ensure_private_dir

            private = ensure_private_dir(Path(root))  # refuses a root inside git, a foreign or an open dir
            try:
                recorder = (
                    _vendor_recorder(scenario, stt, private, budget_usd, vendor_adapter)
                    if mode == 'record-vendor'
                    else _local_recorder(scenario, stt, private, local)
                )
            except LocalRecorderNotInstalled as error:
                raise AudioError(f'record-local: {error}') from None
        misses = recorder.misses
        try:
            cassette = recorder.ensure(
                pcm16,
                language=stt.get('language'),
                vocabulary=tuple(stt.get('vocabulary') or ()),
                purpose=f'stt_cassette:scenario:{mode}',
            )
        except LocalRecorderNotInstalled as error:
            raise AudioError(f'record-local: {error}') from None
        origin = 'recorded' if recorder.misses > misses else 'lab_root'
        out[rec.label] = PreparedAudio(rec.label, pcm16, cassette, origin, mode)
    return out


def _prepare_routed(
    scenario: Any,
    recordings: Sequence[Any],
    env: dict[str, str],
    *,
    mode: str,
    root: Path,
    fixtures: Path,
    budget_usd: Optional[float] = None,
) -> dict[str, PreparedAudio]:
    """Routing on: each recording's cassette comes from production's route under the arm's env.

    Cassettes of every engine are recorded beforehand (one ``record-*`` pass per engine, each pinned); only
    the LID answers (vendor probe, local self-gate stand-in) are recorded here, on a ``record-vendor`` run.
    A legacy upload whose files went to different engines plays each engine's words inside its own files."""
    from testing.pipeline_lab.lanes.audio import load_pcm16
    from testing.pipeline_lab.stt_routing import routing

    if mode == 'record-local':
        raise AudioError('stt routing records LID answers with --stt record-vendor, or replays them with --stt replay')
    try:
        inputs = routing.Inputs.load(env)
        mapping = routing.route_cassettes(env)
        if mode == 'record-vendor':
            # A legacy upload split across engines plays each engine's cassette; an unmapped engine would only be
            # found after every paid probe ran. Refuse before spending.
            missing = [r for r in (routing.PARAKEET, routing.MULTILINGUAL) if not mapping.get(r)]
            if missing:
                raise routing.RoutingError(
                    f'record-vendor needs {routing.CASSETTES_ENV} to map {", ".join(missing)} before any paid probe'
                )
        file_seconds = float(env.get(routing.LEGACY_FILE_SECONDS_ENV) or routing.LEGACY_FILE_SECONDS)
    except (routing.RoutingError, ValueError) as error:
        raise AudioError(f'stt routing: {error}') from None
    from testing.pipeline_lab.store import ensure_private_dir

    private = ensure_private_dir(root)
    record = mode == 'record-vendor'
    ledger = None
    if record:
        if budget_usd is None:
            raise AudioError('record-vendor needs --stt-budget-usd (the hard spend cap for LID probes)')
        from testing.pipeline_lab.ledger import SpendLedger

        ledger = SpendLedger(_record_dir(private, scenario.name) / 'lid_ledger.json', budget_usd=budget_usd)
    lid = routing.LidCache(private, record=record, secret_file=env.get(routing.LID_SECRET_FILE_ENV), ledger=ledger)
    self_lid = routing.SelfLidCache(private, record=record, python=env.get(routing.SELF_LID_PYTHON_ENV))
    pcms = {rec.label: load_pcm16(rec.audio_file) for rec in recordings}

    def route_all() -> dict[str, Any]:
        routes, waiting = {}, False
        for rec in recordings:
            try:
                routes[rec.label] = routing.decide(
                    inputs.user,
                    inputs.conversation(rec.label),
                    pcms[rec.label],
                    lid=lid.decision,
                    self_lid=self_lid.language,
                    legacy_file_seconds=file_seconds,
                )
            except routing.PendingSelfLid:
                waiting = True
            except routing.RoutingError as error:
                raise AudioError(f'recording {rec.label}: {error}') from None
        return routes if not waiting else {}

    with routing.patched_environ(env):
        routes = route_all()
        if not routes:  # a record run queued self-gate windows: classify them in one pass, then route again
            try:
                self_lid.flush()
            except routing.RoutingError as error:
                raise AudioError(f'stt routing: {error}') from None
            routes = route_all()
        unrouted = [rec.label for rec in recordings if rec.label not in routes]
        if unrouted:
            raise AudioError(f'stt routing: no route after the self-gate pass for {", ".join(unrouted[:5])}')
    out: dict[str, PreparedAudio] = {}
    misses: list[str] = []
    for rec in recordings:
        pcm16, route = pcms[rec.label], routes[rec.label]
        engines = sorted({r for _, _, r in route.pieces}) if route.route == routing.MIXED else [route.route]
        found = {}
        for engine in engines:
            pin = {**dict(scenario.stt), **routing.cassette_pin(route, mapping, engine)}
            if not pin.get('provider') or not pin.get('model'):
                misses.append(
                    f'recording {rec.label}: routed to {engine}, which has no cassette pin; map it in '
                    f'{routing.CASSETTES_ENV} ({route.reason})'
                )
                break
            hit = find(pcm16, pin, root=root, fixtures=fixtures)
            if hit is None:
                misses.append(_miss_message(scenario, rec, pcm16, pin) + f' (routed {engine}: {route.reason})')
                break
            found[engine] = hit
        if len(found) != len(engines):
            if not record:
                break
            continue
        cassette, origin = found[engines[0]]
        if len(engines) > 1:
            cassette = _spliced(found, route.pieces)
        summary = {**route.summary(), 'audio_sha256': audio_sha256(pcm16)[:16]}
        out[rec.label] = PreparedAudio(rec.label, pcm16, cassette, origin, mode, route=summary)
    if misses:
        more = f' (+{len(misses) - 1} more)' if len(misses) > 1 else ''
        recorded = lid.calls + self_lid.calls
        raise AudioError(misses[0] + more + (f'; recorded {recorded} LID answer(s)' if recorded else ''))
    return out


def _spliced(found: dict[str, tuple[Cassette, str]], pieces: Sequence[tuple[float, float, str]]) -> Cassette:
    """One cassette for a legacy upload whose files went to different engines: each engine's words that
    start inside its own files (the multilingual engine's key names it)."""
    words = []
    for start, end, engine in pieces:
        words.extend(w for w in found[engine][0].words if start <= w.start < end)
    base = found.get('multilingual', next(iter(found.values())))[0]
    return replace(base, words=sorted(words, key=lambda w: (w.start, w.end)), segments=[])


# ---- materialize (inside the lab environment) -----------------------------------------------------

# What the scenario adds on top of each lane driver's own production/simulated lists.
STAND_INS = {
    'batch': ['speaker_identification(not run: no voiceprints; projection marks every segment is_user=false)'],
    'sync': ['speaker_identification(not run: no voiceprints)', 'sync intake and job (scenario STAND_IN_SYNC)'],
}


def _lines(segments: Sequence[dict[str, Any]], origin: float) -> tuple[Any, ...]:
    from testing.pipeline_lab.scenario.spec import Line

    out = []
    for seg in segments:
        text = str(seg.get('text') or '').strip()
        if not text:
            continue
        out.append(
            Line(
                round(float(seg['start']) + origin, 3),
                round(float(seg['end']) + origin, 3),
                text,
                str(seg.get('speaker') or 'SPEAKER_00'),
                bool(seg.get('is_user', False)),
            )
        )
    return tuple(sorted(out, key=lambda line: (line.start, line.end)))


def materialize(
    scenario: Any,
    prepared: dict[str, PreparedAudio],
    *,
    vad: Optional[Callable] = None,
    file_vad: Optional[Callable] = None,
    scratch_root: Optional[Path] = None,
) -> tuple[Any, dict[str, Any]]:
    """The scenario with every audio recording's ``lines`` filled from its lane replay, and the report.

    ``scratch_root``: where the sync lane's work files go (``<root>/tmp/sync``); default the scenario lab root."""
    from testing.pipeline_lab.cassette.player import SpanSource
    from testing.pipeline_lab.contracts import utc_iso
    from testing.pipeline_lab.lanes.batch import BatchConversation, replay_record_lane
    from testing.pipeline_lab.lanes.sync import SyncConversation, private_scratch, replay_sync_lane

    report: dict[str, Any] = {'mode': next(iter(prepared.values())).mode if prepared else None, 'recordings': []}
    recordings = []
    for rec in scenario.recordings:
        item = prepared.get(rec.label)
        if rec.audio_file is None or item is None:
            recordings.append(rec)
            continue
        start, end = scenario.at(rec.audio[0]), scenario.at(rec.audio[1])
        stt = {'source': item.cassette.source, 'provider': item.cassette.key.provider, 'model': item.cassette.key.model}
        language = item.cassette.key.language if item.cassette.key.language != 'multi' else None
        if rec.lane == 'batch':
            result = replay_record_lane(
                BatchConversation(rec.doc_id, item.pcm16, utc_iso(start), utc_iso(end), language),
                SpanSource(item.cassette),
                vad=vad,
                stt=stt,
                capture_epoch=start.timestamp(),
            )
        else:
            result = replay_sync_lane(
                SyncConversation(rec.doc_id, item.pcm16, utc_iso(start), utc_iso(end), language),
                span=SpanSource(item.cassette),
                file_vad=file_vad,
                stt=stt,
                scratch=private_scratch(scratch_root),  # the recording's WAV files: inside the private lab root
            )
        if result.outcome == 'failed':
            raise AudioError(f'recording {rec.label}: the {rec.lane} lane failed ({result.error})')
        lines = _lines(result.segments, rec.audio[0])
        recordings.append(replace(rec, lines=lines))
        report['recordings'].append(
            {
                'label': rec.label,
                'lane': rec.lane,
                'audio_file': os.path.basename(rec.audio_file),
                **item.summary(),
                'outcome': result.outcome,
                'segments': len(lines),
                'words': sum(len(line.text.split()) for line in lines),
                'driver': result.driver.get('name'),
                'product': list(result.driver.get('production') or []),
                'simulated': list(result.driver.get('simulated') or []) + STAND_INS[rec.lane],
                **({'worker': result.driver.get('worker_counts')} if result.driver.get('worker_counts') else {}),
            }
        )
    return replace(scenario, recordings=tuple(recordings)), report
