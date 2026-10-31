#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Windowed empty-capture census, in-memory VAD, guarded reprocess/hide/undo.

Dry-run is the default. Reports contain aggregate counts only. No audio,
transcript or title is written to disk. Only apply-hide creates a private,
write-ahead rollback ledger containing row identities and content digests.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import fcntl
import importlib
import io
import json
import logging
import math
import os
from pathlib import Path
import random
import secrets
import stat
import sys
import time
from types import SimpleNamespace
import zlib

from google.api_core.exceptions import Aborted, FailedPrecondition, NotFound
from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.conversations.empty_capture_recovery import (
    Changed,
    AuthorityBlocked,
    MutationUncertain,
    STOP_OUTCOMES,
    MARKER,
    OPERATION,
    ROW_FIELDS,
    Observed,
    classify,
    duration_seconds,
    hide_one,
    reprocess_one,
    row_digest,
    speech_bucket,
    undo_one,
)
from scripts.capture_empty_recovery_privacy import Privacy, MaskedClient, atomic_write, marker_blocks

PROJECT = 'based-hardware'
CUSTODY_BUCKET = 'omi-private-cloud-sync'
LEDGER_ROOT = Path('/Volumes/Ephemeral/scratch/capturereprocess')
JOB_FIELDS = ('created_at', 'processing_trigger', 'uid', 'conversation_id', 'requires_byok')
BUCKETS = ('zero', 'under_1s', '1_to_3s', '3_to_10s', 'over_10s')


class Refused(ValueError):
    pass


class DiscardOutput(io.TextIOBase):
    def write(self, value):
        return len(value)


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def utc(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0, 'utc_window_required')
    return stamp


def runtime():
    # Existing codec imports require injected runtime secrets. Keep that
    # boundary out of --help, pure decisions and credential-free unit imports.
    require(len(os.getenv('ENCRYPTION_SECRET', '')) >= 32, 'encryption_secret_required')
    return SimpleNamespace(
        codec=importlib.import_module('database.capture_speech'),
        encryption=importlib.import_module('utils.encryption'),
        source=importlib.import_module('utils.batch_pipeline.source_audio'),
        timeline=importlib.import_module('database.audio_timeline'),
        vad=importlib.import_module('utils.stt.local_vad'),
    )


def sample_eligible(observed, decode):
    row = observed.row
    if (
        observed.trigger != 'server_recovery'
        or observed.rejection is not None
        or observed.requires_byok is not False
        or row.get('uses_custom_stt')
        or row.get('listen_finalization_requires_byok')
        or row.get('status') != 'completed'
        or row.get('deleted')
        or row.get('discarded')
        or row.get('sync_merged_into')
    ):
        return False
    duration = duration_seconds(row)
    if duration is None or not 0 < duration <= 60 or row.get('transcript_segments') is None:
        return False
    try:
        return decode(observed.uid, row['transcript_segments'], bool(row.get('transcript_segments_compressed'))) == []
    except Exception:
        return False


def encode_segments(modules, uid, segments, level):
    require(level in {'standard', 'enhanced'}, 'protection_unproven')
    compressed = zlib.compress(json.dumps(segments).encode('utf-8'))
    return modules.encryption.encrypt(compressed.hex(), uid) if level == 'enhanced' else compressed


class Census:
    def __init__(self, client, pace):
        self.client, self.pace = client, pace
        self.reads = Counter()
        self.privacy = Privacy(client, self.reads)
        self.writes = 0

    def authorize(self, observed):
        self.privacy.check(observed)

    def index_ready(self):
        index = importlib.import_module('utils.conversations.typesense_index')
        require(index.typesense_configured() and index.conversation_index_writes_enabled(), 'index_unavailable')

    def converge(self, observed):
        # Reconciliation reads current durable projection, never a stale patch.
        self.privacy.check(observed, match_revision=False)
        index = importlib.import_module('utils.conversations.typesense_index')
        client = MaskedClient(self.client, self.reads, 'index')
        with redirect_stdout(DiscardOutput()), redirect_stderr(DiscardOutput()):
            return index.sync_conversation_index_after_write(
                observed.uid, observed.conversation_id, firestore_client=client, db_client=client
            )

    def rows(self, after, before, max_jobs):
        query = (
            self.client.collection('conversation_finalization_jobs')
            .where(filter=FieldFilter('status', '==', 'dead_letter'))
            .where(filter=FieldFilter('created_at', '>=', after))
            .where(filter=FieldFilter('created_at', '<', before))
            .order_by('created_at')
            .select(JOB_FIELDS)
        )
        cursor, pairs, scanned = None, {}, 0
        while True:
            page_query = query.start_after(cursor) if cursor else query
            page = list(page_query.limit(min(200, max_jobs + 1 - scanned)).stream(timeout=60, retry=None))
            self.reads['jobs'] += max(1, len(page))
            scanned += len(page)
            require(scanned <= max_jobs, 'job_scan_cap_exceeded')
            if not page:
                break
            for snapshot in page:
                job = snapshot.to_dict() or {}
                uid, cid = job.get('uid'), job.get('conversation_id')
                if isinstance(uid, str) and isinstance(cid, str) and uid and cid and '/' not in uid + cid:
                    pair = (uid, cid)
                    trigger = job.get('processing_trigger')
                    # An ambiguous pair is counted and left unchanged.
                    prior = pairs.get(pair)
                    pairs[pair] = (
                        trigger if prior is None or prior[0] == trigger else 'ambiguous',
                        job.get('requires_byok') is False and (prior is None or prior[1]),
                        (*prior[2], snapshot.id) if prior else (snapshot.id,),
                    )
                else:
                    self.reads['unresolvable_jobs'] += 1
            cursor = page[-1]
            time.sleep(self.pace)
        # Marker policy is shared with serving code. Do not fetch row content
        # for an account whose wipe has begun (including unknown marker states).
        denied = set()
        owners = sorted({uid for uid, _ in pairs})
        for start in range(0, len(owners), 50):
            refs = [self.client.collection('account_deletions').document(uid) for uid in owners[start : start + 50]]
            for snapshot in self.client.get_all(refs, field_paths=('wipe_status',), timeout=60, retry=None):
                self.reads['account_markers'] += 1
                if marker_blocks(snapshot):
                    denied.add(snapshot.id)
            time.sleep(self.pace)
        ordered = []
        for uid, cid in sorted(pairs):
            trigger, managed, jobs = pairs[(uid, cid)]
            rejection = 'account_blocked' if uid in denied else 'byok_or_payer_unproven' if not managed else None
            if rejection:
                yield Observed(uid, cid, {}, None, trigger, managed, jobs, rejection=rejection)
            else:
                ordered.append((uid, cid))
        for start in range(0, len(ordered), 50):
            group = ordered[start : start + 50]
            refs = [
                self.client.collection('users').document(uid).collection('conversations').document(cid)
                for uid, cid in group
            ]
            identities = {ref.path: pair for ref, pair in zip(refs, group)}
            for snapshot in self.client.get_all(refs, field_paths=ROW_FIELDS, timeout=60, retry=None):
                self.reads['conversations'] += 1
                uid, cid = identities[snapshot.reference.path]
                trigger, managed, jobs = pairs[(uid, cid)]
                yield Observed(uid, cid, snapshot.to_dict() or {}, snapshot.update_time, trigger, False, jobs)
            time.sleep(self.pace)

    def current(self, uid, cid):
        snapshot = (
            self.client.collection('users')
            .document(uid)
            .collection('conversations')
            .document(cid)
            .get(field_paths=ROW_FIELDS, timeout=30, retry=None)
        )
        self.reads['conversations'] += 1
        return Observed(uid, cid, snapshot.to_dict() or {}, snapshot.update_time)

    def cas(self, observed, patch):
        ref = (
            self.client.collection('users')
            .document(observed.uid)
            .collection('conversations')
            .document(observed.conversation_id)
        )

        def operation(transaction):
            self.privacy.check(observed, transaction)
            snapshot = (
                MaskedClient(self.client, self.reads, 'conversations')
                .document(ref.path)
                .get(transaction=transaction, timeout=30, retry=None)
            )
            if not snapshot.exists or snapshot.update_time != observed.revision:
                raise Changed()
            transaction.update(ref, patch)

        try:
            revision = atomic_write(self.client, operation)
        except (Changed, AuthorityBlocked):
            raise
        except (Aborted, FailedPrecondition, NotFound):
            raise Changed() from None
        except Exception:
            raise MutationUncertain() from None
        self.writes += 1
        return revision


class Audio:
    """Generation-pinned retained chunks, decoded by the batch source reader."""

    def __init__(self, client, modules, *, authorize, max_seconds=7200):
        self.client, self.modules, self.max_seconds = client, modules, max_seconds
        self.authorize = authorize
        self.counts = Counter()

    def preflight(self):
        opus = importlib.import_module('utils.other.audio_opus')
        opus._get_opuslib()
        self.modules.vad.offline_pcm_speech_segments(bytes(1024))

    def pcm(self, observed):
        self.authorize(observed)
        bucket = self.client.bucket(CUSTODY_BUCKET)
        prefix = f'chunks/{observed.uid}/{observed.conversation_id}/'
        chunks, listed_clocks = [], set()
        self.counts['object_lists'] += 1
        for blob in bucket.list_blobs(prefix=prefix, page_size=200, timeout=30, retry=None):
            require(len(chunks) < 4096, 'audio_object_cap')
            extension = self.modules.timeline.get_extension_for_path(blob.name)
            require(extension in {'opus', 'opus.enc', 'bin', 'enc', 'batch.bin', 'batch.enc'}, 'unknown_audio_codec')
            filename = self.modules.timeline.strip_extension(blob.name.rsplit('/', 1)[-1])
            timestamp = float(filename.split('-', 1)[0])
            require(math.isfinite(timestamp), 'audio_clock_unproven')
            clock = round(timestamp * 1000)
            require(clock not in listed_clocks, 'audio_duplicate_clock_objects')
            listed_clocks.add(clock)
            span = self.modules.timeline.parse_span_blob_metadata(blob.metadata)
            chunks.append((span['start'] if span else timestamp, blob, span))
        require(chunks, 'audio_missing')
        # A partial prefix cannot prove silence. Every chunk referenced by the
        # row must still be present, and every file needs an explicit clock set.
        files = observed.row.get('audio_files')
        require(isinstance(files, list) and files, 'audio_manifest_unproven')
        expected_clocks = set()
        for part in files:
            clocks = part.get('chunk_timestamps') if isinstance(part, dict) else None
            require(isinstance(clocks, list) and clocks, 'audio_manifest_unproven')
            require(all(type(n) in (float, int) and math.isfinite(n) for n in clocks), 'audio_clock_unproven')
            expected_clocks.update(round(n * 1000) for n in clocks)
        require(expected_clocks <= listed_clocks, 'audio_partial_missing')
        require(listed_clocks == expected_clocks, 'audio_unreferenced_objects')
        chunks.sort(key=lambda item: (item[0], item[1].name))
        key = self.modules.encryption.derive_key(observed.uid)
        origin, output, previous_end = chunks[0][0], bytearray(), 0
        for timestamp, blob, span in chunks:
            ref = {
                'path': blob.name,
                'bucket': CUSTODY_BUCKET,
                'generation': blob.generation,
                'metadata': blob.metadata or {},
                'sample_rate': int(
                    (blob.metadata or {}).get('record_sample_rate', span['sample_rate'] if span else 16000)
                ),
            }
            # read_reference validates owner path, generation and encoded size,
            # then authenticates enhanced encryption before codec decoding.
            self.counts['object_reads'] += 1
            pcm = self.modules.source.read_reference(
                self.client, ref, observed.uid, observed.conversation_id, {CUSTODY_BUCKET}, key
            )
            require(pcm and len(pcm) % 2 == 0, 'audio_decode_unproven')
            start = round((timestamp - origin) * 16000)
            end = start + len(pcm) // 2
            require(0 <= start < end <= self.max_seconds * 16000, 'audio_duration_cap')
            if span:
                require(
                    abs(len(pcm) // 2 / 16000 - span['samples'] / span['sample_rate']) <= 0.05, 'audio_extent_mismatch'
                )
            overlap = max(0, min(previous_end, end) - start)
            if overlap:
                require(output[start * 2 : (start + overlap) * 2] == pcm[: overlap * 2], 'audio_overlap_unproven')
            if end > previous_end:
                if start > previous_end:
                    output.extend(bytes((start - previous_end) * 2))
                output.extend(pcm[overlap * 2 :])
                previous_end = end
            del pcm
        return bytes(output)

    def measure(self, observed):
        pcm = self.pcm(observed)
        try:
            spans = self.modules.vad.offline_pcm_speech_segments(pcm)
            seconds = math.fsum(span['duration'] for span in spans)
            speech_bucket(seconds)
            return seconds, len(pcm) / 32000
        finally:
            del pcm

    def transcribe(self, observed):
        pcm = self.pcm(observed)
        try:
            return self.transcribe_pcm(observed, pcm)
        finally:
            del pcm

    def transcribe_pcm(self, observed, pcm):
        try:
            # Same single-call CPU recovery recognizer and response/VAD checks
            # as utils/batch_pipeline, without its projection/enrichment writes.
            recognizers = importlib.import_module('utils.batch_pipeline.recovery_recognizers')
            hashes = importlib.import_module('utils.conversations.transcript_hash')
            item = SimpleNamespace(duration_seconds=len(pcm) / 32000)
            with redirect_stdout(DiscardOutput()), redirect_stderr(DiscardOutput()):
                # Use the existing recovery VAD/response contract and provider
                # path, with a fresh privacy/payer check after CPU preparation
                # and immediately before its one paid dispatch.
                _, duration, spans = recognizers.inspect_audio(item, recognizers.canonical_wav(pcm))
                require(spans, 'no_measured_speech')
                output = recognizers.canonical_wav(pcm)
                provider = importlib.import_module('utils.stt.pre_recorded')
                self.authorize(observed)
                response = provider.modulate_prerecorded_from_bytes(
                    output, language=None, return_language=True, attempts=2
                )
                words, language = recognizers.validate_response(response, duration, spans, multilingual=True)
                payload = recognizers.words_payload(duration, spans, words, language)
            segments = [
                {
                    'text': word['word'],
                    'start': word['timestamp'][0],
                    'end': word['timestamp'][1],
                    'speaker': word.get('speaker', 'SPEAKER_00'),
                    'is_user': False,
                    'person_id': None,
                }
                for word in payload['words']
            ]
            return hashes.canonicalize_transcript_segments_for_storage(segments)
        finally:
            del pcm


class Ledger:
    """Exclusive, mode-0600 write-ahead file, with no audio or content payloads."""

    def __init__(self, path, *, create=False):
        path = Path(path)
        require(
            path.is_absolute() and path.parent.resolve() == LEDGER_ROOT and not path.is_symlink(),
            'private_ledger_path_required',
        )
        LEDGER_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(stat.S_IMODE(LEDGER_ROOT.stat().st_mode) == 0o700, 'private_ledger_directory_required')
        flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0)
        fd = os.open(path, flags, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            os.close(fd)
            raise Refused('private_ledger_mode_required')
        self.file = os.fdopen(fd, 'r+', encoding='utf-8')
        fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def token(self):
        return secrets.token_hex(16)

    def append(self, body):
        self.file.seek(0, os.SEEK_END)
        self.file.write(json.dumps(body, sort_keys=True) + '\n')
        self.file.flush()
        os.fsync(self.file.fileno())

    def prepare(self, observed, marker):
        self.append(
            {
                'event': 'prepared',
                'uid': observed.uid,
                'conversation_id': observed.conversation_id,
                'marker': marker,
                'prior_discarded': observed.row.get('discarded', False),
                'before_sha256': row_digest(observed.row),
            }
        )

    def committed(self, token, revision):
        self.append({'event': 'committed', 'token': token, 'revision': revision.isoformat()})

    def entries(self):
        self.file.seek(0)
        entries, committed = [], {}
        for line in self.file:
            body = json.loads(line)
            if body.get('event') == 'prepared':
                require(body['marker']['operation'] == OPERATION, 'ledger_operation_mismatch')
                entries.append(body)
            elif body.get('event') == 'committed':
                committed[body['token']] = body['revision']
            else:
                raise Refused('ledger_event_unproven')
        for entry in entries:
            entry['committed_revision'] = committed.get(entry['marker']['token'])
        return entries

    def close(self):
        self.file.close()


def wilson(successes, total):
    if not total:
        return [0.0, 1.0]
    z = 1.959963984540054
    p, denominator = successes / total, 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('action', choices=('census', 'measure', 'reprocess', 'hide', 'undo', 'index'))
    result.add_argument('--after')
    result.add_argument('--before')
    result.add_argument('--max-jobs', type=int, default=20000)
    result.add_argument('--pace-seconds', type=float, default=0.5)
    result.add_argument('--sample-size', type=int, default=400)
    result.add_argument('--seed', type=int, default=20261031)
    result.add_argument('--apply', action='store_true')
    result.add_argument('--concurrency', type=int)
    result.add_argument('--max-count', type=int)
    result.add_argument('--max-audio-seconds', type=float)
    result.add_argument('--ledger')
    result.add_argument(
        '--include-short-speech',
        action='store_true',
        help='Reprocess measured short speech too; zero/unreadable stays unchanged',
    )
    return result


def run(args):
    require(not args.apply or args.action in {'reprocess', 'hide', 'undo', 'index'}, 'action_read_only')
    require(0.1 <= args.pace_seconds <= 60 and 1 <= args.max_jobs <= 100000, 'invalid_scan_budget')
    require(
        not args.apply or (args.concurrency == 1 and args.max_count and 0 < args.max_count <= 1000),
        'explicit_serial_count_cap_required',
    )
    require(
        not args.apply or (args.max_audio_seconds and 0 < args.max_audio_seconds <= 7200), 'explicit_audio_cap_required'
    )
    require(not args.apply or os.getenv('GCP_AGENT_TIER') not in {'ro-prod', 'ro-dev'}, 'read_only_tier')
    require(not args.apply or os.getenv('CAPTURE_EMPTY_APPLY_AUTHORIZED') == OPERATION, 'apply_authorization_required')
    modules = runtime()
    census = Census(firestore.Client(project=PROJECT), args.pace_seconds)
    audio = Audio(
        storage.Client(project=PROJECT),
        modules,
        authorize=census.authorize,
        max_seconds=args.max_audio_seconds or 7200,
    )
    if args.apply and args.action in {'hide', 'undo', 'index'}:
        census.index_ready()
    if args.action == 'measure' or (args.apply and args.action in {'hide', 'reprocess'}):
        audio.preflight()
    decode = modules.codec.decode_capture_segments

    def encode(uid, segments, level):
        return encode_segments(modules, uid, segments, level)

    output = {
        'mode': 'apply' if args.apply else 'dry_run',
        'counts': {},
        'outcomes': {},
        'firestore_writes': 0,
        'stopped': False,
    }
    ledger = None
    try:
        if args.action in {'undo', 'index'}:
            require(args.ledger, 'undo_ledger_required')
            ledger = Ledger(args.ledger)
            outcomes = Counter()
            entries = ledger.entries()
            for number, entry in enumerate(entries):
                if args.apply and number >= args.max_count:
                    break
                current = census.current(entry['uid'], entry['conversation_id'])
                if args.action == 'index':
                    # Only reconcile this ledger's rows, using their current
                    # projection; never replay discarded/transcript mutations.
                    outcome = 'would_reconcile'
                    if args.apply:
                        try:
                            outcome = 'reconciled' if census.converge(current) else 'visibility_index_unproven'
                        except AuthorityBlocked:
                            outcome = 'authority_blocked'
                else:
                    outcome = undo_one(
                        current,
                        entry,
                        cas=census.cas if args.apply else lambda *_: None,
                        converge=census.converge if args.apply else lambda _: True,
                    )
                outcomes['would_restore' if not args.apply and outcome == 'restored' else outcome] += 1
                if outcome in STOP_OUTCOMES:
                    output['stopped'] = True
                    break
                time.sleep(args.pace_seconds)
            output['outcomes'] = dict(outcomes)
            output['firestore_writes'] = census.writes
        else:
            require(args.after and args.before, 'explicit_window_required')
            after, before = utc(args.after), utc(args.before)
            require(after < before <= datetime.now(timezone.utc), 'invalid_time_window')
            rows = list(census.rows(after, before, args.max_jobs))
            decisions = [(row, classify(row, decode)) for row in rows]
            counts = Counter(decision for _, decision in decisions)
            output['counts'] = dict(counts)
            output['reprocess_base_candidates'] = counts['reprocess_long'] + counts['reprocess_shell']
            output['hide_candidates_unmeasured'] = counts['short_needs_measurement']
            print(
                json.dumps(
                    {
                        'census': output['counts'],
                        'document_reads_so_far': sum(v for k, v in census.reads.items() if k != 'unresolvable_jobs'),
                    }
                ),
                flush=True,
            )
            short = [row for row in rows if sample_eligible(row, decode)]
            output['empty_short_population'] = len(short)
            if args.action == 'measure':
                require(300 <= args.sample_size <= 2000 and len(short) >= 300, 'sample_floor_300_required')
                sample = random.Random(args.seed).sample(short, min(args.sample_size, len(short)))
                buckets, failures, eligible_hide, speech_reprocess = Counter(), Counter(), 0, 0
                for index, row in enumerate(sample):
                    try:
                        speech, decoded_seconds = audio.measure(row)
                        require(decoded_seconds <= 60.05, 'decoded_not_short')
                        buckets[speech_bucket(speech)] += 1
                        if classify(row, decode) == 'short_needs_measurement':
                            eligible_hide += speech == 0
                            speech_reprocess += speech > 0
                    except Exception as error:
                        reason = (
                            str(error)
                            if isinstance(error, Refused)
                            else 'authority_blocked' if isinstance(error, AuthorityBlocked) else 'audio_unreadable'
                        )
                        # Refused is constructed only from fixed literals above.
                        failures[reason] += 1
                    if (index + 1) % 25 == 0:
                        print(json.dumps({'progress': index + 1, 'sample_size': len(sample)}), flush=True)
                    time.sleep(args.pace_seconds)
                output['sample_size'] = len(sample)
                output['speech_buckets'] = {
                    bucket: {
                        'n': buckets[bucket],
                        'share_of_sample': buckets[bucket] / len(sample),
                        'wilson95': wilson(buckets[bucket], len(sample)),
                        'estimated_rows': round(len(short) * buckets[bucket] / len(sample)),
                    }
                    for bucket in BUCKETS
                }
                output['audio_failures'] = dict(failures)
                output['audio_unmeasured'] = sum(failures.values())
                output['zero_speech_sample_rows'] = buckets['zero']
                output['sample_hide_eligible'] = eligible_hide
                output['sample_short_speech_reprocess_eligible'] = speech_reprocess
                output['short_speech_sample_reprocess'] = len(sample) - sum(failures.values()) - buckets['zero']
            elif args.action in {'hide', 'reprocess'}:
                selected = [
                    row
                    for row, decision in decisions
                    if decision
                    in (
                        {'short_needs_measurement'}
                        if args.action == 'hide'
                        else {'reprocess_long', 'reprocess_shell'}
                        | ({'short_needs_measurement'} if args.include_short_speech else set())
                    )
                ]
                outcomes, spent_audio = Counter(), 0.0
                if args.apply:
                    selected = selected[: args.max_count]
                    if args.action == 'hide':
                        require(args.ledger, 'hide_ledger_required')
                        ledger = Ledger(args.ledger, create=True)
                for row in selected:
                    if not args.apply:
                        outcomes['unmeasured_keep' if args.action == 'hide' else 'reprocess_candidate'] += 1
                        continue
                    if args.action == 'hide':
                        try:
                            speech, decoded_seconds = audio.measure(row)
                            require(decoded_seconds <= 60.05, 'decoded_not_short')
                            require(spent_audio + decoded_seconds <= args.max_audio_seconds, 'audio_budget_unproven')
                            spent_audio += decoded_seconds
                            outcome = hide_one(
                                row, speech, decode=decode, cas=census.cas, ledger=ledger, converge=census.converge
                            )
                        except Exception:
                            outcome = 'audio_unproven_keep'
                    else:
                        pcm = None
                        try:
                            # Prove retained audio before claiming the row. The
                            # actual decoded count, not duration metadata, spends
                            # the invocation's total audio budget, shells included.
                            pcm = audio.pcm(row)
                            duration = len(pcm) / 32000
                            require(spent_audio + duration <= args.max_audio_seconds, 'audio_budget_unproven')
                            spent_audio += duration
                            speech = None
                            if classify(row, decode) == 'short_needs_measurement':
                                speech = math.fsum(
                                    span['duration'] for span in modules.vad.offline_pcm_speech_segments(pcm)
                                )
                            outcome = reprocess_one(
                                row,
                                decode=decode,
                                encode=encode,
                                cas=census.cas,
                                transcribe=lambda observed: audio.transcribe_pcm(observed, pcm),
                                speech_seconds=speech,
                            )
                        except Exception:
                            outcome = 'audio_budget_or_custody_unproven'
                        finally:
                            del pcm
                    outcomes[outcome] += 1
                    if outcome in STOP_OUTCOMES:
                        output['stopped'] = True
                        break
                    time.sleep(args.pace_seconds)
                output['outcomes'] = dict(outcomes)
                output['firestore_writes'] = census.writes if args.apply else 0
    finally:
        if ledger:
            ledger.close()
    output['firestore_reads'] = dict(census.reads)
    output['total_document_reads'] = sum(v for k, v in census.reads.items() if k != 'unresolvable_jobs')
    output['audio_io'] = dict(audio.counts)
    print(json.dumps(output, sort_keys=True), flush=True)
    return output


def main():
    args = parser().parse_args()
    # Some legacy helpers log identifiers and provider bodies. The CLI owns a
    # stricter counts-only boundary, including dependency stdout and stderr.
    logging.disable(logging.CRITICAL)
    try:
        output = run(args)
    except Refused as error:
        print(json.dumps({'outcome': 'refused', 'reason': str(error)}))
        return 2
    except Exception:
        print(json.dumps({'outcome': 'error', 'reason': 'operation_failed_closed'}))
        return 1
    return 2 if output['stopped'] else 0


if __name__ == '__main__':
    sys.exit(main())
