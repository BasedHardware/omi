import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Sync cooldowns are per lane. The regression these cover: the sync pages gated the Sync
/// control on the account-wide `isLimited`, while uploads gate on `isLimitedForLane`. A
/// fair-use cooldown does not block the backfill lane, so a backlog that uploads through
/// backfill was left with no Sync button and no automatic drain — the app refusing a sync its
/// own upload path would have accepted.

SyncRateLimiter get limiter => SyncRateLimiter.instance;

const int _hour = 3600;

Wal _wal({required int ageSeconds, String? conversationId, int nowSeconds = 1000000}) => Wal(
      timerStart: nowSeconds - ageSeconds,
      codec: BleAudioCodec.opus,
      seconds: 30,
      conversationId: conversationId,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    limiter.clear();
  });

  group('pendingSyncUploadLanes', () {
    const now = 1000000;

    test('a recent recording with server capture proof is fresh', () {
      final lanes = pendingSyncUploadLanes([_wal(ageSeconds: _hour, conversationId: 'conv-1')], now);
      expect(lanes, {SyncUploadLane.fresh});
    });

    test('an old recording is backfill even with capture proof', () {
      final lanes = pendingSyncUploadLanes([_wal(ageSeconds: 48 * _hour, conversationId: 'conv-1')], now);
      expect(lanes, {SyncUploadLane.backfill});
    });

    test('a recording with no conversation is backfill however recent', () {
      final lanes = pendingSyncUploadLanes([_wal(ageSeconds: 60)], now);
      expect(lanes, {SyncUploadLane.backfill});
    });

    test('a mixed backlog reports both lanes', () {
      final lanes = pendingSyncUploadLanes([
        _wal(ageSeconds: _hour, conversationId: 'conv-1'),
        _wal(ageSeconds: 48 * _hour, conversationId: 'conv-2'),
      ], now);
      expect(lanes, {SyncUploadLane.fresh, SyncUploadLane.backfill});
    });

    test('nothing pending reports no lanes', () {
      expect(pendingSyncUploadLanes(const [], now), isEmpty);
    });
  });

  group('allSyncLanesLimited', () {
    bool onlyFreshLimited(String lane) => lane == SyncUploadLane.fresh.name;

    test('a backlog on a free lane is not blocked by another lane cooldown', () {
      expect(
        allSyncLanesLimited({SyncUploadLane.backfill}, onlyFreshLimited, fallback: true),
        isFalse,
      );
    });

    test('work on the limited lane is blocked', () {
      expect(allSyncLanesLimited({SyncUploadLane.fresh}, onlyFreshLimited, fallback: false), isTrue);
    });

    test('a mixed backlog is not blocked while either lane is free', () {
      expect(
        allSyncLanesLimited({SyncUploadLane.fresh, SyncUploadLane.backfill}, onlyFreshLimited, fallback: true),
        isFalse,
      );
    });

    test('every lane limited is blocked', () {
      expect(
        allSyncLanesLimited({SyncUploadLane.fresh, SyncUploadLane.backfill}, (_) => true, fallback: false),
        isTrue,
      );
    });

    test('with nothing pending the fallback decides', () {
      expect(allSyncLanesLimited(const {}, (_) => false, fallback: true), isTrue);
      expect(allSyncLanesLimited(const {}, (_) => true, fallback: false), isFalse);
    });
  });

  group('the UI gate matches the upload gate', () {
    test('a fair-use cooldown leaves a backfill backlog actionable', () {
      limiter.markLimited(retryAfterSeconds: 30 * 24 * _hour, reason: RateLimitReason.fairUse);

      // What the old UI read: account-wide, and true.
      expect(limiter.isLimited, isTrue);
      // What the upload path reads: the backfill lane is free, so an upload would be accepted.
      expect(limiter.isLimitedForLane(SyncUploadLane.backfill.name), isFalse);

      // The gate the UI now reads must agree with the upload path, or it hides a sync that works.
      final blocked = allSyncLanesLimited(
        {SyncUploadLane.backfill},
        limiter.isLimitedForLane,
        fallback: limiter.isLimited,
      );
      expect(blocked, isFalse);
    });

    test('a fair-use cooldown still blocks fresh work', () {
      limiter.markLimited(retryAfterSeconds: 1800, reason: RateLimitReason.fairUse);

      expect(limiter.isLimitedForLane(SyncUploadLane.fresh.name), isTrue);
      expect(
        allSyncLanesLimited({SyncUploadLane.fresh}, limiter.isLimitedForLane, fallback: limiter.isLimited),
        isTrue,
      );
    });

    test('a backend-busy cooldown blocks both lanes', () {
      limiter.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.backendBusy);

      expect(
        allSyncLanesLimited(
          {SyncUploadLane.fresh, SyncUploadLane.backfill},
          limiter.isLimitedForLane,
          fallback: limiter.isLimited,
        ),
        isTrue,
      );
    });
  });

  group('backfill reconciliation', () {
    test('a stale fair-use cooldown self-heals on a backfill upload', () async {
      SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch + 60000);
      SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
      var statusFetches = 0;
      final gate = SyncUploadGate(
        limiter: limiter,
        fairUseStatusLoader: () async {
          statusFetches++;
          return {'stage': 'none'};
        },
        uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
            UploadFilesResult.queued('job-1'),
      );

      final allowed = await gate.prepareToUpload(lane: SyncUploadLane.backfill);

      // Previously the backfill lane skipped reconciliation entirely, so the persisted cooldown
      // outlived the server state that had already cleared.
      expect(statusFetches, 1);
      expect(allowed, isTrue);
      expect(limiter.hasPersistedFairUseState, isFalse);
      expect(limiter.isLimited, isFalse);
    });

    test('reconciliation is skipped when nothing is persisted', () async {
      var statusFetches = 0;
      final gate = SyncUploadGate(
        limiter: limiter,
        fairUseStatusLoader: () async {
          statusFetches++;
          return {'stage': 'none'};
        },
        uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
            UploadFilesResult.queued('job-2'),
      );

      expect(await gate.prepareToUpload(lane: SyncUploadLane.backfill), isTrue);
      expect(statusFetches, 0);
    });
  });

  // Static wiring check, not behavioural coverage: the widget tree is not exercised here, so
  // this only pins which getter the pages read. The behaviour it protects is covered above.
  group('sync pages read the lane-aware gate (static)', () {
    for (final path in const [
      'lib/pages/conversations/auto_sync_page.dart',
      'lib/pages/conversations/sync_page.dart',
    ]) {
      test(path, () {
        final source = File(path).readAsStringSync();
        expect(source.contains('isRateLimitedForPendingUploads'), isTrue,
            reason: '$path must gate on the lanes the pending work needs');
        expect(RegExp(r'isRateLimited\b(?!ForPendingUploads)').hasMatch(source), isFalse,
            reason: '$path must not gate on the account-wide cooldown; uploads gate per lane');
      });
    }
  });
}
