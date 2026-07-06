import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const appleTeamId = 'GRSWQKJR57';
  const mainBundleId = 'dev.moni11811.omi';
  const widgetBundleId = 'dev.moni11811.omi.widget';
  const appGroupBuildSetting = r'group.$(APP_BUNDLE_IDENTIFIER)';
  const legacyTeamId = '9536L8KLMP';
  const legacyAppGroupId = 'group.com.friend-app-with-wearable.ios12';

  String read(String path) => File(path).readAsStringSync();

  test('dev iOS signing matches logged-in Apple developer account', () {
    for (final config in ['devDebug', 'devProfile', 'devRelease']) {
      expect(
        read('ios/Flutter/$config.xcconfig'),
        contains('APP_BUNDLE_IDENTIFIER=$mainBundleId'),
      );
    }

    final project = read('ios/Runner.xcodeproj/project.pbxproj');
    expect(project, contains('DEVELOPMENT_TEAM = $appleTeamId;'));
    expect(project, isNot(contains('DEVELOPMENT_TEAM = $legacyTeamId;')));
    expect(
      project,
      contains('PRODUCT_BUNDLE_IDENTIFIER = "\$(APP_BUNDLE_IDENTIFIER)";'),
    );
    expect(
      project,
      contains('PRODUCT_BUNDLE_IDENTIFIER = "\$(APP_BUNDLE_IDENTIFIER).widget";'),
    );

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
    }

    expect(read('ios/BatteryWidget/SharedDefaults.swift'), contains('Bundle.main.bundleIdentifier'));
    expect(read('ios/Runner/AppDelegate.swift'), contains('appGroupIdentifier'));
    expect(widgetBundleId, '$mainBundleId.widget');
  });
}
