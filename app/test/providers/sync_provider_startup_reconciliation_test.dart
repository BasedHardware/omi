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
      uploader: (files, {onUploadProgress, conversationId}) async => UploadFilesResult.queued('unused'),
    );
    final provider = SyncProvider(walService: WalService(), uploadGate: gate, startBackgroundSync: false);

    await provider.initialized;

    expect(statusCalls, 1);
    expect(limiter.hasPersistedFairUseState, isFalse);
    expect(limiter.isLimited, isFalse);
    provider.dispose();
  });
}
