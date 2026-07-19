import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/user_provider.dart';

void main() {
  group('UserProvider private cloud sync loading', () {
    test('applies the fetched value on success', () async {
      final provider = UserProvider(privateCloudSyncFetcher: () async => true);
      addTearDown(provider.dispose);

      await provider.loadPrivateCloudSyncStatus();

      expect(provider.privateCloudSyncEnabled, isTrue);
    });

    test('preserves the enabled state when a fetch fails (returns null)', () async {
      // Regression for #9466: a transient GET failure returned false, silently
      // flipping the cloud-sync toggle off even though it was still enabled.
      bool? result = true;
      final provider = UserProvider(privateCloudSyncFetcher: () async => result);
      addTearDown(provider.dispose);

      await provider.loadPrivateCloudSyncStatus();
      expect(provider.privateCloudSyncEnabled, isTrue);

      // Next load fails (no response / non-200) — must not turn the toggle off.
      result = null;
      await provider.loadPrivateCloudSyncStatus();

      expect(provider.privateCloudSyncEnabled, isTrue);
    });

    test('preserves the enabled state when the fetch throws', () async {
      var shouldThrow = false;
      final provider = UserProvider(
        privateCloudSyncFetcher: () async {
          if (shouldThrow) throw Exception('network down');
          return true;
        },
      );
      addTearDown(provider.dispose);

      await provider.loadPrivateCloudSyncStatus();
      expect(provider.privateCloudSyncEnabled, isTrue);

      shouldThrow = true;
      await provider.loadPrivateCloudSyncStatus();

      expect(provider.privateCloudSyncEnabled, isTrue);
    });
  });

  group('UserProvider private cloud sync writing', () {
    test('applies the value on a successful write', () async {
      final provider = UserProvider(privateCloudSyncSetter: (_) async => true);
      addTearDown(provider.dispose);

      await provider.setPrivateCloudSync(true);

      expect(provider.privateCloudSyncEnabled, isTrue);
    });

    test('throws and keeps the old state when the write is rejected', () async {
      // Regression for #9466 (write path): setPrivateCloudSyncEnabled returns
      // false on a rejected write (no response / non-200 / status != ok). The
      // provider used to swallow it, so the UI showed a success snackbar while
      // the toggle snapped back off — the user believed cloud storage was on
      // and lost recordings. A rejected write must surface as an error.
      final provider = UserProvider(privateCloudSyncSetter: (_) async => false);
      addTearDown(provider.dispose);

      await expectLater(provider.setPrivateCloudSync(true), throwsException);
      expect(provider.privateCloudSyncEnabled, isFalse);
    });

    test('rethrows when the write throws', () async {
      final provider = UserProvider(
        privateCloudSyncSetter: (_) async => throw Exception('network down'),
      );
      addTearDown(provider.dispose);

      await expectLater(provider.setPrivateCloudSync(true), throwsException);
      expect(provider.privateCloudSyncEnabled, isFalse);
    });
  });
}
