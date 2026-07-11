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
}
