import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppProvider.toggleApp', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    late AppProvider provider;

    tearDown(() {
      provider.dispose();
    });

    test('returns false when enableAppServer fails (regression guard)', () async {
      provider = AppProvider();
      provider.enableAppOverride = (String id) async {
        expect(id, equals('app_123'));
        return (false, '');
      };

      final result = await provider.toggleApp('app_123', true, null);

      // The entire purpose of the #10100 fix: the caller can now
      // distinguish failure from success instead of assuming success.
      expect(result, isFalse);
    });

    test('returns true when enableAppServer succeeds', () async {
      provider = AppProvider();
      // Set up local app so the success path can find and update it.
      provider.apps = [
        App(
          id: 'app_123',
          name: 'Test',
          author: 'tester',
          description: 'test',
          image: '',
          capabilities: {'memories'},
          status: 'approved',
          category: 'test',
          approved: true,
          ratingCount: 0,
          enabled: true,
          deleted: false,
          isPaid: false,
          isUserPaid: false,
        ),
      ];
      var enableCalled = false;
      provider.enableAppOverride = (String id) async {
        enableCalled = true;
        expect(id, equals('app_123'));
        return (true, '');
      };

      final result = await provider.toggleApp('app_123', true, null);

      expect(result, isTrue);
      expect(enableCalled, isTrue);
    });

    test('does not call enableAppOverride when disabling', () async {
      provider = AppProvider();
      var enableCalled = false;
      provider.enableAppOverride = (String id) async {
        enableCalled = true;
        return (true, '');
      };
      provider.disableAppOverride = (String id) async {
        expect(id, equals('app_456'));
        return true;
      };

      final result = await provider.toggleApp('app_456', false, null);

      expect(result, isTrue);
      expect(enableCalled, isFalse); // only disableAppOverride was used
    });

    test('returns false and keeps local state enabled when disableAppServer rejects', () async {
      provider = AppProvider();
      provider.apps = [
        App(
          id: 'app_456',
          name: 'Test',
          author: 'tester',
          description: 'test',
          image: '',
          capabilities: {'memories'},
          status: 'approved',
          category: 'test',
          approved: true,
          ratingCount: 0,
          enabled: true,
          deleted: false,
          isPaid: false,
          isUserPaid: false,
        ),
      ];
      provider.disableAppOverride = (String id) async {
        expect(id, equals('app_456'));
        return false;
      };

      final result = await provider.toggleApp('app_456', false, null);

      expect(result, isFalse);
      expect(provider.apps.single.enabled, isTrue);
    });
  });
}
