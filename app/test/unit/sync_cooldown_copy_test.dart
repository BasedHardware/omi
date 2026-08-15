import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/pages/conversations/sync_cooldown_copy.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

void main() {
  final l = AppLocalizationsEn();

  group('syncCooldownTitle', () {
    test('never reuses the neutral ready-count copy', () {
      // #10948: backfillPaced mapped to syncCardReadyCount, so a sync stalled
      // behind a re-arming cooldown read as ordinary pending work for a full
      // day. Every reason, present and future, must read as a cooldown.
      final readyCounts = [for (var count = 0; count < 30; count++) l.syncCardReadyCount(count)];

      for (final reason in [null, ...RateLimitReason.values]) {
        final title = syncCooldownTitle(reason, l);
        expect(title, isNotEmpty, reason: '$reason has no cooldown copy');
        expect(readyCounts, isNot(contains(title)), reason: '$reason renders as the benign ready-count');
      }
    });

    test('distinguishes a server capacity pause from a fair-use restriction', () {
      expect(syncCooldownTitle(RateLimitReason.backendBusy, l), l.syncCardBackendBusy);
      expect(syncCooldownTitle(RateLimitReason.fairUse, l), l.syncCardRateLimited);
    });
  });
}
