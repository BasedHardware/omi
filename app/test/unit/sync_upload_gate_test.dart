import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:shared_preferences/shared_preferences.dart';

SyncRateLimiter get limiter => SyncRateLimiter.instance;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    limiter.clear();
  });

  test('stale persisted fair-use cooldown self-heals before upload', () async {
    SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch - 1000);
    SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('job-1');
      },
    );

    final result = await gate.upload([]);

    expect(result.jobId, 'job-1');
    expect(uploads, 1);
    expect(limiter.hasPersistedFairUseState, isFalse);
  });

  test('natural expiry normalized to throttle clears persisted hard restriction', () async {
    SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch - 1000);
    SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'throttle'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('job-after-expiry');
      },
    );

    final result = await gate.upload([]);

    expect(result.jobId, 'job-after-expiry');
    expect(uploads, 1);
    expect(limiter.hasPersistedFairUseState, isFalse);
  });

  test('failed status fetch preserves and rearms an expired explicit restriction', () async {
    SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch - 1000);
    SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => null,
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('unexpected');
      },
    );

    await expectLater(gate.upload([]), throwsA(isA<SyncRateLimitedException>()));

    expect(uploads, 0);
    expect(limiter.isFairUseLimited, isTrue);
  });

  test('unknown authoritative stage fails closed and preserves explicit restriction', () async {
    SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch - 1000);
    SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'future_stage'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('unexpected');
      },
    );

    await expectLater(gate.upload([]), throwsA(isA<SyncRateLimitedException>()));

    expect(uploads, 0);
    expect(limiter.isFairUseLimited, isTrue);
  });

  test('legacy unclassified rateLimit state never blocks admission or becomes fair use offline', () async {
    SharedPreferencesUtil().saveInt(
      'syncRateLimitedUntilMs',
      DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
    );
    SharedPreferencesUtil().saveString('syncRateLimitedReason', 'rateLimit');
    var statusCalls = 0;
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async {
        statusCalls++;
        throw Exception('offline');
      },
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('legacy-cleared');
      },
    );

    final result = await gate.upload([]);

    expect(result.jobId, 'legacy-cleared');
    expect(statusCalls, 0);
    expect(uploads, 1);
    expect(limiter.hasPersistedFairUseState, isFalse);
    expect(limiter.isLimited, isFalse);
    expect(limiter.reason, isNull);
  });

  test('real restriction is preserved and blocks upload after local expiry', () async {
    SharedPreferencesUtil().saveInt('syncRateLimitedUntilMs', DateTime.now().millisecondsSinceEpoch - 1000);
    SharedPreferencesUtil().saveString('syncRateLimitedReason', RateLimitReason.fairUse.name);
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'restrict'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        return UploadFilesResult.queued('unexpected');
      },
    );

    await expectLater(
      gate.upload([]),
      throwsA(isA<SyncRateLimitedException>().having((error) => error.kind, 'kind', SyncRateLimitKind.fairUse)),
    );

    expect(uploads, 0);
    expect(limiter.isFairUseLimited, isTrue);
  });

  test('fair-use reconciliation is single-flight', () async {
    limiter.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.fairUse);
    final response = Completer<Map<String, dynamic>?>();
    var statusCalls = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () {
        statusCalls++;
        return response.future;
      },
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
          UploadFilesResult.queued('job'),
    );

    final first = gate.reconcileFairUseStatus();
    final second = gate.reconcileFairUseStatus();
    expect(statusCalls, 1);

    response.complete({'stage': 'none'});
    expect(await first, isTrue);
    expect(await second, isTrue);
    expect(limiter.hasPersistedFairUseState, isFalse);
  });

  test('fair-use clear preserves a distinct backend-capacity cooldown', () async {
    limiter.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.fairUse);
    limiter.markLimited(retryAfterSeconds: 1200, reason: RateLimitReason.backendBusy);
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
          UploadFilesResult.queued('job'),
    );

    expect(await gate.reconcileFairUseStatus(), isFalse);
    expect(limiter.hasPersistedFairUseState, isFalse);
    expect(limiter.isBackendBusyLimited, isTrue);
    expect(limiter.reason, RateLimitReason.backendBusy);
  });

  test('one generic 429 closes admission and caps capacity backoff at 24 hours', () async {
    var uploads = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => null,
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        throw SyncRateLimitedException(kind: SyncRateLimitKind.backendCapacity, retryAfterSeconds: 40 * 24 * 60 * 60);
      },
    );

    final results = await Future.wait([
      gate.upload([]).then<Object>((value) => value).catchError((Object error) => error),
      gate.upload([]).then<Object>((value) => value).catchError((Object error) => error),
    ]);

    expect(uploads, 1);
    expect(results, everyElement(isA<SyncRateLimitedException>()));
    expect(limiter.reason, RateLimitReason.backendBusy);
    expect(limiter.hasPersistedFairUseState, isFalse);
    expect(limiter.activeRetryAfterSeconds, inInclusiveRange(24 * 60 * 60 - 2, 24 * 60 * 60));
  });

  test('explicit fair-use 429 persists and admits the full 30-day Retry-After', () async {
    var uploads = 0;
    var statusCalls = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async {
        statusCalls++;
        return {'stage': 'none'};
      },
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploads++;
        throw SyncRateLimitedException(kind: SyncRateLimitKind.fairUse, retryAfterSeconds: 30 * 24 * 60 * 60);
      },
    );

    final results = await Future.wait([
      gate.upload([]).then<Object>((value) => value).catchError((Object error) => error),
      gate.upload([]).then<Object>((value) => value).catchError((Object error) => error),
    ]);

    expect(results, everyElement(isA<SyncRateLimitedException>()));
    expect(uploads, 1);
    expect(statusCalls, 0);
    expect(limiter.reason, RateLimitReason.fairUse);
    expect(limiter.hasPersistedFairUseState, isTrue);
    expect(limiter.activeRetryAfterSeconds, inInclusiveRange(30 * 24 * 60 * 60 - 2, 30 * 24 * 60 * 60));
  });

  test('backfill pacing persists without blocking a fresh upload', () async {
    final uploadedLanes = <SyncUploadLane>[];
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        uploadedLanes.add(syncLane);
        return UploadFilesResult.queued('fresh-job');
      },
    );
    limiter.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.backfillPaced);

    await expectLater(
      gate.upload([], lane: SyncUploadLane.backfill),
      throwsA(isA<SyncRateLimitedException>().having((error) => error.kind, 'kind', SyncRateLimitKind.backfillPaced)),
    );
    final fresh = await gate.upload([], lane: SyncUploadLane.fresh);

    expect(fresh.jobId, 'fresh-job');
    expect(uploadedLanes, [SyncUploadLane.fresh]);
    expect(limiter.isBackfillLimited, isTrue);
  });

  test('backfill responses are passed to the uploader as a lane hint', () async {
    SyncUploadLane? seenLane;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => null,
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async {
        seenLane = syncLane;
        return UploadFilesResult.queued('backfill-job');
      },
    );

    await gate.upload([], lane: SyncUploadLane.backfill);

    expect(seenLane, SyncUploadLane.backfill);
  });
}
