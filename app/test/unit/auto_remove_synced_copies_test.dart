import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('auto-remove synced copies default migration', () {
    test('existing onboarded install is pinned OFF', () async {
      SharedPreferences.setMockInitialValues({'onboardingCompleted': true});
      await SharedPreferencesUtil.init();

      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isFalse);
    });

    test('fresh install before onboarding keeps the ON default and stays unmarked', () async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool('autoRemoveSyncedCopiesDefaultMigrated'), isNull);
    });

    test('an explicit user choice is never overwritten', () async {
      SharedPreferences.setMockInitialValues({'onboardingCompleted': true, 'autoRemoveSyncedCopies': true});
      await SharedPreferencesUtil.init();

      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
    });

    test('migration runs once; a later re-enable survives relaunch', () async {
      SharedPreferences.setMockInitialValues({'onboardingCompleted': true});
      await SharedPreferencesUtil.init();
      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isFalse);

      // The user opts in after upgrading.
      SharedPreferencesUtil().autoRemoveSyncedCopies = true;
      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
    });

    test('signing out clears the marker so the next account migrates again', () async {
      SharedPreferences.setMockInitialValues({
        'onboardingCompleted': true,
        'autoRemoveSyncedCopiesDefaultMigrated': true,
      });
      await SharedPreferencesUtil.init();

      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('onboardingCompleted');
      await prefs.remove('autoRemoveSyncedCopiesDefaultMigrated');
      await SharedPreferencesUtil.reload();

      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      // Signed-out device is not onboarded: stays on the ON default, unmarked.
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
      expect((await SharedPreferences.getInstance()).getBool('autoRemoveSyncedCopiesDefaultMigrated'), isNull);
    });
  });
}
