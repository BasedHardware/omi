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

    test('fresh install before onboarding keeps the ON default and is marked pre-onboarding', () async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();

      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool('autoRemoveSyncedCopiesDefaultMigrated'), isTrue);
    });

    test('a fresh install that onboards after first launch still defaults ON', () async {
      // Launch 1: brand-new install, pre-onboarding.
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);

      // The user onboards during launch 1.
      SharedPreferencesUtil().onboardingCompleted = true;

      // Launch 2: migration must NOT pin the now-onboarded install OFF.
      await SharedPreferencesUtil.reload();
      await SharedPreferencesUtil().migrateAutoRemoveSyncedCopiesDefault();
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
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

    test('a signed-out install is marked as pre-onboarding and keeps the ON default', () async {
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

      // Signed-out device is not onboarded: re-marked as a pre-onboarding
      // install, which keeps the ON default and blocks any later upgrade-style
      // OFF pinning for the next account.
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, isTrue);
      expect((await SharedPreferences.getInstance()).getBool('autoRemoveSyncedCopiesDefaultMigrated'), isTrue);
    });
  });
}
