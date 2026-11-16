#!/usr/bin/env python3
"""Operator control for TIMELINESS_METRICS-only participation suppression (SCA-1649).

Contract: ``sampler-control-design-amended.md``. This helper captures the exact
prior typed state of ``{namespace}_control/timeliness_metrics_participation``,
plans one bounded suppression, applies it with Firestore ``update_time`` CAS,
restores the exact prior state and verifies the restoration.

Firestore has no server-side dry-run, so ``--dry-run=server`` is rejected.
``--dry-run=emulator`` validates forward and restore against a loopback emulator
and a ``batch_pipeline_test_*`` namespace; local schema/plan/diff checks are
additional, never substitutes. No production dry-run exists.

Every command is bounded: one capture read, one apply read plus one write, one
restore read plus one write, one verification read. No retries, no scans, no
lease access, no guessed defaults.
"""

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.api_core.datetime_helpers import DatetimeWithNanoseconds  # noqa: E402
from google.cloud import firestore  # noqa: E402

from database.batch_pipeline_store import FirestoreStore  # noqa: E402
from utils.batch_pipeline import timeliness_participation as participation  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')


class Refused(Exception):
    """A CAS, conflict or precondition refusal. Nothing was written."""


# --- lossless typed serialization -------------------------------------------------


def tag(value):
    """Encode one Firestore value with its type, losslessly."""
    if value is None:
        return {'t': 'null'}
    if isinstance(value, bool):
        return {'t': 'bool', 'v': value}
    if isinstance(value, int):
        return {'t': 'int', 'v': str(value)}
    if isinstance(value, float):
        return {'t': 'float', 'v': repr(value)}
    if isinstance(value, str):
        return {'t': 'str', 'v': value}
    if isinstance(value, bytes):
        return {'t': 'bytes', 'v': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dt.datetime):
        encoded = {'t': 'timestamp', 'v': value.isoformat()}
        nanosecond = getattr(value, 'nanosecond', 0)
        if nanosecond:
            encoded['ns'] = int(nanosecond)
        return encoded
    if isinstance(value, firestore.GeoPoint):
        return {'t': 'geopoint', 'lat': value.latitude, 'lon': value.longitude}
    if isinstance(value, firestore.DocumentReference):
        return {'t': 'reference', 'v': value.path}
    if isinstance(value, (list, tuple)):
        return {'t': 'list', 'v': [tag(item) for item in value]}
    if isinstance(value, dict):
        return {'t': 'map', 'v': {str(key): tag(item) for key, item in value.items()}}
    raise TypeError(f'unsupported Firestore value type: {type(value).__name__}')


def untag(encoded):
    """Decode one tagged value back to its exact Firestore type."""
    kind = encoded['t']
    if kind == 'null':
        return None
    if kind == 'bool':
        return bool(encoded['v'])
    if kind == 'int':
        return int(encoded['v'])
    if kind == 'float':
        return float(encoded['v'])
    if kind == 'str':
        return encoded['v']
    if kind == 'bytes':
        return base64.b64decode(encoded['v'])
    if kind == 'timestamp':
        parsed = dt.datetime.fromisoformat(encoded['v'])
        nanosecond = int(encoded.get('ns', 0))
        if not nanosecond:
            return parsed
        return DatetimeWithNanoseconds(
            parsed.year,
            parsed.month,
            parsed.day,
            parsed.hour,
            parsed.minute,
            parsed.second,
            tzinfo=parsed.tzinfo,
            nanosecond=nanosecond,
        )
    if kind == 'geopoint':
        return firestore.GeoPoint(encoded['lat'], encoded['lon'])
    if kind == 'reference':
        raise TypeError('document references are not restorable by this helper')
    if kind == 'list':
        return [untag(item) for item in encoded['v']]
    if kind == 'map':
        return {key: untag(item) for key, item in encoded['v'].items()}
    raise TypeError(f'unknown tagged type: {kind}')


def tag_fields(fields):
    return {name: tag(value) for name, value in fields.items()}


def untag_fields(encoded):
    return {name: untag(value) for name, value in encoded.items()}


def fields_digest(encoded_fields):
    canonical = json.dumps(encoded_fields, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


# --- transport --------------------------------------------------------------------


def _is_loopback(host):
    name = host.rsplit(':', 1)[0].strip('[]')
    return name in LOOPBACK_HOSTS


def resolve_store(namespace, *, emulator_host=None):
    """Build the data-plane store, refusing every unsafe transport combination."""
    if emulator_host:
        host = emulator_host.strip()
        if not _is_loopback(host):
            raise Refused(f'emulator host must be loopback, got {host!r}')
        if not namespace.startswith('batch_pipeline_test_'):
            raise Refused('emulator mode requires a batch_pipeline_test_* namespace')
        os.environ['FIRESTORE_EMULATOR_HOST'] = host
    elif namespace.startswith('batch_pipeline_test_'):
        raise Refused('a batch_pipeline_test_* namespace requires --dry-run=emulator')
    return FirestoreStore(namespace)


def _snapshot_state(snapshot):
    if not getattr(snapshot, 'exists', False):
        return {'exists': False, 'update_time': None, 'fields': {}}
    return {
        'exists': True,
        'update_time': tag(snapshot.update_time),
        'fields': tag_fields(snapshot.to_dict() or {}),
    }


def _read(store):
    return participation.read_control(store)


# --- commands ---------------------------------------------------------------------


def capture(store, *, plane):
    """One read: the complete typed prior state, including arbitrary extra fields."""
    state = _snapshot_state(_read(store))
    return {
        'namespace': store.namespace,
        'document': participation.DOCUMENT_ID,
        'plane': plane,
        'captured_at': tag(dt.datetime.now(dt.timezone.utc)),
        'exists': state['exists'],
        'update_time': state['update_time'],
        'fields': state['fields'],
        'fields_sha256': fields_digest(state['fields']),
    }


def build_plan(prior, *, operation_id, created_at, until):
    """Validate the suppression window and bind it to the captured prior state."""
    if not operation_id or len(operation_id.encode('utf-8')) > participation.MAX_OPERATION_ID_BYTES:
        raise Refused('operation_id must be 1..128 UTF-8 bytes')
    if created_at.tzinfo is None or until.tzinfo is None:
        raise Refused('created_at and until must be timezone-aware UTC')
    if not until > created_at:
        raise Refused('until must be after created_at')
    if (until - created_at).total_seconds() > participation.MAX_LIFETIME_SECONDS:
        raise Refused('suppression lifetime must not exceed 1800s')
    now = dt.datetime.now(dt.timezone.utc)
    if created_at > now + dt.timedelta(seconds=participation.MAX_FUTURE_SKEW_SECONDS):
        raise Refused('created_at is beyond the 60s clock-skew allowance')
    fields = {
        'version': participation.SCHEMA_VERSION,
        'target_plane': participation.GKE_PLANE,
        'created_at': created_at,
        'suppressed_until': until,
        'operation_id': operation_id,
    }
    return {
        'namespace': prior['namespace'],
        'document': participation.DOCUMENT_ID,
        'target_plane': participation.GKE_PLANE,
        'operation_id': operation_id,
        'created_at': tag(created_at),
        'suppressed_until': tag(until),
        'fields': tag_fields(fields),
        'prior': {
            'exists': prior['exists'],
            'update_time': prior['update_time'],
            'fields_sha256': prior['fields_sha256'],
        },
    }


def apply_plan(store, plan, *, mode):
    """One read plus one CAS write. A concurrent writer is refused, never overwritten."""
    snapshot = _read(store)
    current = _snapshot_state(snapshot)
    prior = plan['prior']
    if current['exists'] != prior['exists']:
        raise Refused('control document existence changed since capture')
    if current['exists'] and current['update_time'] != prior['update_time']:
        raise Refused('control document changed since capture (update_time mismatch)')
    if current['exists'] and fields_digest(current['fields']) != prior['fields_sha256']:
        raise Refused('control document fields changed since capture')
    fields = untag_fields(plan['fields'])
    reference = participation.control_document(store)
    if current['exists']:
        reference.update(fields, option=firestore.LastUpdateOption(snapshot.update_time), retry=None)
    else:
        reference.create(fields, retry=None)
    applied = _snapshot_state(_read(store))
    return {
        'namespace': store.namespace,
        'document': participation.DOCUMENT_ID,
        'operation_id': plan['operation_id'],
        'mode': mode,
        'applied_update_time': applied['update_time'],
        'applied_fields_sha256': fields_digest(applied['fields']),
        'prior_fields_sha256': prior['fields_sha256'],
    }


def restore_prior(store, prior, applied, *, mode):
    """One read plus one CAS write that restores existence and every typed field."""
    snapshot = _read(store)
    current = _snapshot_state(snapshot)
    if not current['exists']:
        raise Refused('control document is absent; refusing to guess a restoration')
    if current['update_time'] != applied['applied_update_time']:
        raise Refused('control document changed since apply (update_time mismatch)')
    reference = participation.control_document(store)
    if prior['exists']:
        prior_fields = untag_fields(prior['fields'])
        removals = {name: firestore.DELETE_FIELD for name in current['fields'] if name not in prior_fields}
        reference.update(
            {**prior_fields, **removals},
            option=firestore.LastUpdateOption(snapshot.update_time),
            retry=None,
        )
    else:
        reference.delete(option=firestore.LastUpdateOption(snapshot.update_time), retry=None)
    restored = _snapshot_state(_read(store))
    return {
        'namespace': store.namespace,
        'document': participation.DOCUMENT_ID,
        'operation_id': applied['operation_id'],
        'mode': mode,
        'restored_exists': restored['exists'],
        'restored_fields_sha256': fields_digest(restored['fields']),
        'prior_fields_sha256': prior['fields_sha256'],
        'exact': restored['exists'] == prior['exists'] and fields_digest(restored['fields']) == prior['fields_sha256'],
        'restored_update_time': restored['update_time'],
    }


def verify_restored(store, prior):
    """One read: existence plus every typed field/value must match the capture."""
    current = _snapshot_state(_read(store))
    differences = []
    if current['exists'] != prior['exists']:
        differences.append('existence')
    else:
        prior_fields = prior['fields']
        for name in sorted(set(prior_fields) | set(current['fields'])):
            if prior_fields.get(name) != current['fields'].get(name):
                differences.append(name)
    return {
        'namespace': store.namespace,
        'document': participation.DOCUMENT_ID,
        'restored': not differences,
        'differences': differences,
        'current_fields_sha256': fields_digest(current['fields']),
        'prior_fields_sha256': prior['fields_sha256'],
        'update_time': current['update_time'],
    }


# --- CLI --------------------------------------------------------------------------


def _dry_run(value):
    if value == 'server':
        raise argparse.ArgumentTypeError(
            'Firestore has no server-side dry-run; use --dry-run=emulator against a loopback emulator'
        )
    if value != 'emulator':
        raise argparse.ArgumentTypeError('only --dry-run=emulator is supported')
    return value


def _timestamp_arg(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f'invalid UTC timestamp: {value!r}') from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError('timestamp must carry a UTC offset')
    return parsed


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _emulator_namespace(args, plan_namespace=None):
    if getattr(args, 'dry_run', None) == 'emulator':
        if not args.namespace:
            raise Refused('--dry-run=emulator requires --namespace batch_pipeline_test_*')
        return args.namespace
    if args.namespace and plan_namespace and args.namespace != plan_namespace:
        raise Refused('--namespace may not override the plan namespace outside emulator mode')
    return plan_namespace


def _default_applied_path(plan_path):
    return str(Path(plan_path).with_suffix('.applied.json'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)

    capture_parser = subparsers.add_parser('capture', help='capture the exact prior typed state')
    capture_parser.add_argument('--namespace', required=True)
    capture_parser.add_argument('--plane', default=participation.GKE_PLANE)
    capture_parser.add_argument('--out', required=True)
    capture_parser.add_argument('--emulator-host')

    plan_parser = subparsers.add_parser('plan', help='build one bounded suppression plan')
    plan_parser.add_argument('--prior', required=True)
    plan_parser.add_argument('--operation-id', required=True)
    plan_parser.add_argument('--created-at', required=True, type=_timestamp_arg)
    plan_parser.add_argument('--until', required=True, type=_timestamp_arg)
    plan_parser.add_argument('--out', required=True)

    apply_parser = subparsers.add_parser('apply', help='apply the plan with update_time CAS')
    apply_parser.add_argument('--plan', required=True)
    apply_parser.add_argument('--receipt')
    apply_parser.add_argument('--dry-run', type=_dry_run)
    apply_parser.add_argument('--emulator-host')
    apply_parser.add_argument('--namespace')

    restore_parser = subparsers.add_parser('restore', help='restore the exact prior typed state')
    restore_parser.add_argument('--prior', required=True)
    restore_parser.add_argument('--plan')
    restore_parser.add_argument('--applied')
    restore_parser.add_argument('--receipt')
    restore_parser.add_argument('--dry-run', type=_dry_run)
    restore_parser.add_argument('--emulator-host')
    restore_parser.add_argument('--namespace')

    verify_parser = subparsers.add_parser('verify-restored', help='compare the document to the capture')
    verify_parser.add_argument('--prior', required=True)
    verify_parser.add_argument('--emulator-host')
    verify_parser.add_argument('--namespace')

    args = parser.parse_args(argv)

    try:
        if args.command == 'capture':
            store = resolve_store(args.namespace, emulator_host=args.emulator_host)
            payload = capture(store, plane=args.plane)
            _write(args.out, payload)
            print(json.dumps({'captured': True, 'exists': payload['exists'], 'out': args.out}))
            return EXIT_OK

        if args.command == 'plan':
            prior = _load(args.prior)
            payload = build_plan(
                prior,
                operation_id=args.operation_id,
                created_at=args.created_at,
                until=args.until,
            )
            _write(args.out, payload)
            print(json.dumps({'planned': True, 'operation_id': payload['operation_id'], 'out': args.out}))
            return EXIT_OK

        if args.command == 'apply':
            plan = _load(args.plan)
            namespace = _emulator_namespace(args, plan['namespace'])
            if args.dry_run != 'emulator' and not args.receipt:
                raise Refused('a production apply requires --receipt')
            store = resolve_store(namespace, emulator_host=args.emulator_host)
            receipt = apply_plan(store, plan, mode='emulator' if args.dry_run == 'emulator' else 'production')
            receipt_path = args.receipt or _default_applied_path(args.plan)
            _write(receipt_path, receipt)
            print(json.dumps({'applied': True, 'receipt': receipt_path, 'mode': receipt['mode']}))
            return EXIT_OK

        if args.command == 'restore':
            prior = _load(args.prior)
            if args.dry_run == 'emulator':
                if not args.plan:
                    raise Refused('emulator restore requires --plan')
                plan = _load(args.plan)
                namespace = _emulator_namespace(args, plan['namespace'])
                applied_path = args.receipt or _default_applied_path(args.plan)
                if not Path(applied_path).exists():
                    raise Refused('emulator restore requires the emulator apply receipt')
                applied = _load(applied_path)
                mode = 'emulator'
            else:
                if not args.applied:
                    raise Refused('a production restore requires --applied')
                applied = _load(args.applied)
                namespace = _emulator_namespace(args, prior['namespace'])
                mode = 'production'
            store = resolve_store(namespace, emulator_host=args.emulator_host)
            receipt = restore_prior(store, prior, applied, mode=mode)
            if args.receipt:
                _write(args.receipt, receipt)
            print(json.dumps(receipt))
            return EXIT_OK if receipt['exact'] else EXIT_REFUSED

        if args.command == 'verify-restored':
            prior = _load(args.prior)
            namespace = _emulator_namespace(args, prior['namespace'])
            store = resolve_store(namespace, emulator_host=args.emulator_host)
            result = verify_restored(store, prior)
            print(json.dumps(result))
            return EXIT_OK if result['restored'] else EXIT_REFUSED

        raise Refused(f'unknown command: {args.command}')
    except Refused as error:
        print(json.dumps({'refused': True, 'reason': str(error)}), file=sys.stderr)
        return EXIT_REFUSED
    except Exception as error:  # Bounded failure: report the exact type, never retry.
        print(json.dumps({'error': type(error).__name__, 'detail': str(error)}), file=sys.stderr)
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
