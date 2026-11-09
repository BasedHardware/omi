#!/usr/bin/env python3
"""Offline captured-hour union adapter. No production reads or billing queries.

Input: retained source-manifest JSONL, with physical identity and half-open
source-frame ranges. Output is aggregate-only; never exports owner identities.
Lifecycle: rollout, default off; owner pipeline-approved; review 2026-11-21.
"""

import argparse
import hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fractions import Fraction
import json
import math
import os
from pathlib import Path

IDENTITY = ('owner', 'capture_root', 'device', 'channel', 'clock_epoch')
REQUIRED_COSTS = frozenset({'cloud', 'gpu_fleet', 'notes_llm', 'composer_llm', 'vendor_stt', 'network_logging'})


def union(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def captured_hours(rows):
    sources, clocks, bad = defaultdict(list), {}, set()
    unknown = 0
    batch = defaultdict(list)
    for row in rows:
        identity = tuple(row.get(field) for field in IDENTITY)
        try:
            if not all(isinstance(value, str) and value for value in identity):
                raise ValueError('physical identity unavailable')
            rate, start, end = (row.get(field) for field in ('sample_rate', 'start_frame', 'end_frame'))
            if any(type(value) is not int for value in (rate, start, end)) or rate <= 0 or start < 0 or end <= start:
                raise ValueError('source frame range unavailable')
            if not isinstance(row.get('epoch_started_at'), str):
                raise ValueError('source clock unavailable')
            epoch = datetime.fromisoformat(row['epoch_started_at'].replace('Z', '+00:00'))
            if epoch.tzinfo is None:
                raise ValueError('source clock has no timezone')
            clock = (rate, Fraction(str(epoch.timestamp())))
            if identity in clocks and clocks[identity] != clock:
                bad.add(identity)
                raise ValueError('inconsistent physical clock')
            clocks[identity] = clock
            sources[identity].append((start, end))
            if row.get('path') == 'batch':
                batch[identity].append((start, end))
        except (KeyError, TypeError, ValueError, OverflowError):
            unknown += 1
    days, batch_days = defaultdict(Fraction), defaultdict(Fraction)

    def split(intervals, identity, target):
        rate, epoch = clocks[identity]
        for start, end in union(intervals):
            cursor, finish = epoch + Fraction(start, rate), epoch + Fraction(end, rate)
            while cursor < finish:
                at = datetime.fromtimestamp(float(cursor), timezone.utc)
                midnight = at.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                boundary = min(finish, Fraction(str(midnight.timestamp())))
                target[at.date().isoformat()] += (boundary - cursor) / 3600
                cursor = boundary

    for identity, intervals in sources.items():
        if identity not in bad:
            split(intervals, identity, days)
            split(batch[identity], identity, batch_days)
    return {
        'captured_audio_hours': {day: float(hours) for day, hours in sorted(days.items())},
        'batch_captured_audio_hours': {day: float(hours) for day, hours in sorted(batch_days.items())},
        'unknown_manifest_rows': unknown,
        'conflicting_physical_sources': len(bad),
        'physical_capture_roots': len(sources) - len(bad),
        'manifest_ranges_valid': unknown == 0 and not bad and bool(sources),
        'denominator_complete': False,  # Valid rows alone cannot prove inventory coverage.
        'inventory_receipt': None,
    }


def verify_inventory_coverage(capture, proof, manifest_digest, *, now=None):
    """Require a fresh aggregate inventory attestation for this exact export."""
    now = now or datetime.now(timezone.utc)
    verified = False
    try:
        generated = datetime.fromisoformat(proof['generated_at'].replace('Z', '+00:00'))
        valid_until = datetime.fromisoformat(proof['valid_until'].replace('Z', '+00:00'))
        verified = bool(
            capture['manifest_ranges_valid']
            and proof.get('complete') is True
            and proof.get('source') == 'retained_capture_manifest_inventory'
            and proof.get('unknown_capture_roots') == 0
            and proof.get('physical_capture_roots') == capture['physical_capture_roots']
            and proof.get('captured_audio_hours') == capture['captured_audio_hours']
            and set(capture['captured_audio_hours']) <= set(proof.get('covered_utc_days', []))
            and proof.get('manifest_sha256') == manifest_digest
            and isinstance(proof.get('source_receipt'), str)
            and proof['source_receipt'].strip()
            and generated <= now <= valid_until
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    return {
        **capture,
        'denominator_complete': verified,
        'inventory_receipt': proof['source_receipt'] if verified else None,
        'inventory_generated_at': generated.isoformat() if verified else None,
        'valid_until': valid_until.isoformat() if verified else None,
    }


def inventory_current(capture, *, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        generated = datetime.fromisoformat(capture['inventory_generated_at'])
        expires = datetime.fromisoformat(capture['valid_until'])
        return bool(
            capture.get('denominator_complete') is True
            and capture.get('manifest_ranges_valid') is True
            and isinstance(capture.get('inventory_receipt'), str)
            and capture['inventory_receipt'].strip()
            and generated <= now <= expires
        )
    except (KeyError, TypeError, ValueError):
        return False


def revalidate_report(capture, *, now=None):
    """No old aggregate can republish prices after its inventory proof expires."""
    if inventory_current(capture, now=now):
        return capture
    return {
        **capture,
        'denominator_complete': False,
        'cost': {
            day: {**row, 'pipeline_cost_usd': None, 'usd_per_captured_audio_hour': None, 'status': 'unknown'}
            for day, row in capture.get('cost', {}).items()
        },
    }


def cost_per_captured_hour(capture, costs, *, now=None):
    """Cost input must already be reconciled and allocated to captured UTC day.

    gpu_fleet includes idle and busy; its invoice lines must be excluded from
    cloud. Processing-day/transcription-second allocation is ineligible.
    """
    result = {}
    for day, hours in capture['captured_audio_hours'].items():
        row = costs.get(day, {})
        components = row.get('components', {})
        known = (
            inventory_current(capture, now=now)
            and row.get('reconciled') is True
            and row.get('basis') == 'captured_utc_day'
            and row.get('gpu_excluded_from_cloud') is True
            and set(components) == REQUIRED_COSTS
            and bool(row.get('source_receipts'))
            and all(
                isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
                for value in components.values()
            )
        )
        result[day] = {
            'pipeline_cost_usd': sum(components.values()) if known else None,
            'usd_per_captured_audio_hour': sum(components.values()) / hours if known and hours > 0 else None,
            'status': 'reconciled' if known and hours > 0 else 'unknown',
        }
    return result


def rewrite_census(receipts):
    """One latest durable automatic-note count per conversation, no IDs exported."""
    versions = {}
    unknown = 0
    for receipt in receipts:
        owner, conversation = receipt.get('owner_key'), receipt.get('conversation_id')
        count = receipt.get('notes_versions')
        if not owner or not conversation or type(count) is not int or count < 1:
            unknown += 1
            continue
        identity = owner, conversation
        versions[identity] = max(versions.get(identity, 0), count)
    distribution = defaultdict(int)
    for count in versions.values():
        distribution[count - 1] += 1
    return {
        'omi_pipeline_notes_rewrites_per_conversation': dict(sorted(distribution.items())),
        'conversations': len(versions),
        'unknown_receipts': unknown,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifests', type=Path, required=True)
    parser.add_argument('--costs', type=Path)
    parser.add_argument(
        '--inventory-coverage',
        type=Path,
        help='Fresh aggregate inventory proof bound to the consumed manifest SHA256 and UTC days',
    )
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument(
        '--notes-receipts',
        type=Path,
        help='Metadata-only protected receipt export for a unique-conversation rewrite census',
    )
    args = parser.parse_args(argv)
    if os.getenv('PIPELINE_CAPTURE_COST_ENABLED', 'false').strip().lower() != 'true':
        parser.exit(0, 'captured-hour reporting disabled; prior reports are stale\n')
    manifest_hash = hashlib.sha256()

    def manifests():
        with args.manifests.open('rb') as source:
            for line in source:
                manifest_hash.update(line)
                if line.strip():
                    yield json.loads(line)

    result = captured_hours(manifests())
    if args.inventory_coverage:
        result = verify_inventory_coverage(
            result, json.loads(args.inventory_coverage.read_text()), manifest_hash.hexdigest()
        )
    result['cost'] = cost_per_captured_hour(result, json.loads(args.costs.read_text()) if args.costs else {})
    if args.notes_receipts:
        result['notes_rewrites'] = rewrite_census(
            json.loads(line) for line in args.notes_receipts.read_text().splitlines() if line.strip()
        )
    result['generated_at'] = datetime.now(timezone.utc).isoformat()
    result['sources'] = {
        'capture': 'retained_source_manifest_export',
        'cost': 'reconciled_captured_day_cost_export' if args.costs else None,
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
