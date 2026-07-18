import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('provider startup reconciles and clears persisted fair-use restriction', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final limiter = SyncRateLimiter.instance;
    limiter.clear();
    limiter.markLimited(retryAfterSeconds: 3600, reason: RateLimitReason.fairUse);
    var statusCalls = 0;
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async {
        statusCalls++;
        return {'stage': 'none'};
      },
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
          UploadFilesResult.queued('unused'),
    );
    final provider = SyncProvider(walService: WalService(), uploadGate: gate, startBackgroundSync: false);

    await provider.initialized;

    expect(statusCalls, 1);
    expect(limiter.hasPersistedFairUseState, isFalse);
    expect(limiter.isLimited, isFalse);
    provider.dispose();
  });

  test('provider waits for persisted WAL readiness before attaching startup recovery', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final readiness = Completer<void>();
    final limiter = SyncRateLimiter.instance..clear();
    final gate = SyncUploadGate(
      limiter: limiter,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files, {onUploadProgress, conversationId, syncLane = SyncUploadLane.fresh}) async =>
          UploadFilesResult.queued('unused'),
    );
    var startupWakes = 0;
    final provider = SyncProvider(
      walService: WalService(),
      uploadGate: gate,
      waitForWalReady: (_) => readiness.future,
      startRecovery: () async {
        startupWakes++;
      },
    );
    var initialized = false;
    unawaited(provider.initialized.then((_) => initialized = true));

    await Future<void>.delayed(Duration.zero);
    expect(initialized, isFalse);
    expect(startupWakes, 0);

    readiness.complete();
    await provider.initialized;

    expect(initialized, isTrue);
    expect(startupWakes, 1);
    provider.dispose();
  });
}
