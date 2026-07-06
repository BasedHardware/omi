import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String read(String path) => File(path).readAsStringSync();

void main() {
  group('review blocker contracts', () {
    test('iOS App Group follows the active flavor and Swift uses the same value', () {
      const appGroupBuildSetting = r'group.$(APP_BUNDLE_IDENTIFIER)';
      const legacyAppGroupId = 'group.com.friend-app-with-wearable.ios12';
      const devAppGroupId = 'group.dev.moni11811.omi';

      for (final entitlementPath in [
        'ios/Runner/Runner.entitlements',
        'ios/Runner/RunnerDebug-dev.entitlements',
        'ios/Runner/RunnerProfile-dev.entitlements',
        'ios/Runner/RunnerRelease-dev.entitlements',
        'ios/BatteryWidget/BatteryWidget.entitlements',
      ]) {
        final entitlements = read(entitlementPath);
        expect(entitlements, contains(appGroupBuildSetting), reason: entitlementPath);
        expect(entitlements, isNot(contains(legacyAppGroupId)), reason: entitlementPath);
        expect(entitlements, isNot(contains(devAppGroupId)), reason: entitlementPath);
      }

      final sharedDefaults = read('ios/BatteryWidget/SharedDefaults.swift');
      expect(sharedDefaults, contains('Bundle.main.bundleIdentifier'));
      expect(sharedDefaults, isNot(contains('let appGroupIdentifier = "group.')));

      final appDelegate = read('ios/Runner/AppDelegate.swift');
      expect(appDelegate, contains('appGroupIdentifier'));
      expect(appDelegate, isNot(contains('UserDefaults(suiteName: "group.')));

      final project = read('ios/Runner.xcodeproj/project.pbxproj');
      expect(project, contains('APP_BUNDLE_IDENTIFIER = dev.moni11811.omi;'));
      expect(project, contains('APP_BUNDLE_IDENTIFIER = "com.friend-app-with-wearable.ios12";'));
    });

    test('Meta Wearables DAT token is injected at build time', () {
      final tokenLiteral = RegExp(r'AR\|\d+\|[A-Fa-f0-9]{32}');

      for (final path in [
        'android/app/src/main/AndroidManifest.xml',
        'android/app/build.gradle',
        'ios/Runner/Info.plist',
        'ios/Flutter/devDebug.xcconfig',
        'ios/Flutter/devProfile.xcconfig',
        'ios/Flutter/devRelease.xcconfig',
        'ios/Flutter/prodDebug.xcconfig',
        'ios/Flutter/prodProfile.xcconfig',
        'ios/Flutter/prodRelease.xcconfig',
        'ios/Flutter/Base.xcconfig',
      ]) {
        expect(read(path), isNot(matches(tokenLiteral)), reason: path);
      }

      expect(read('android/app/src/main/AndroidManifest.xml'), contains(r'${metaWearablesClientToken}'));
      expect(read('android/app/build.gradle'), contains('META_WEARABLES_CLIENT_TOKEN'));
      expect(read('ios/Runner/Info.plist'), contains(r'$(META_WEARABLES_CLIENT_TOKEN)'));
      expect(read('ios/Flutter/Base.xcconfig'), contains('META_WEARABLES_CLIENT_TOKEN=0'));
    });

    test('production Apple Sign-In default stays enabled', () {
      final prodEnv = read('lib/env/prod_env.dart');
      expect(prodEnv, contains("varName: 'APPLE_SIGN_IN_ENABLED'"));
      expect(prodEnv, contains('defaultValue: true'));
    });

    test('Android BLE foreground service persists for background and batch capture', () {
      final mainActivity = read('android/app/src/main/kotlin/com/example/my_project/MainActivity.kt');
      expect(mainActivity, contains('isPersistentModeEnabled(this)'));
      expect(mainActivity, isNot(contains('if (!OmiBleForegroundService.isBackgroundModeEnabled(this))')));

      final companionService = read('android/app/src/main/kotlin/com/friend/ios/BleCompanionService.kt');
      expect(companionService, contains('isPersistentModeEnabled(applicationContext)'));
      expect(companionService,
          isNot(contains('if (!OmiBleForegroundService.isBackgroundModeEnabled(applicationContext))')));
    });

    test('profile async callbacks check mounted before setState', () {
      final profile = read('lib/pages/settings/profile.dart');
      expect(profile, contains('if (!mounted || !sheetContext.mounted) return;'));
      expect(profile, isNot(contains('.whenComplete(() => setState')));
    });
  });
}
