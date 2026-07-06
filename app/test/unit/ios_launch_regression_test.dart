import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

String _read(String path) => File(path).readAsStringSync();

void main() {
  group('iOS launch regressions', () {
    test('Runner keeps the legacy UIKit lifecycle (no UIScene opt-in)', () {
      // Adopting UIScene (UIApplicationSceneManifest in Info.plist) makes
      // UIApplication.shared.delegate.window nil during
      // didFinishLaunchingWithOptions. flutter_contacts (and potentially other
      // plugins) force-unwrap that window in register(with:), which traps with
      // EXC_BREAKPOINT before Dart starts — 11 identical device crash reports
      // on 2026-07-05 all faulted in SwiftFlutterContactsPlugin.register.
      //
      // The UIScene requirement only applies to binaries linked against the
      // iOS 27 SDK (Xcode-beta). Build with the default stable Xcode instead;
      // sdk<27 binaries keep the legacy lifecycle on iOS 27 devices.
      final plist = _read('ios/Runner/Info.plist');
      expect(plist, isNot(contains('UIApplicationSceneManifest')),
          reason: 'UIScene opt-in crashes plugin registration (flutter_contacts window force-unwrap). '
              'Do not re-add the scene manifest until every registered plugin is scene-safe.');

      final pubspec = _read('pubspec.yaml');
      expect(pubspec, contains('flutter_contacts'),
          reason: 'If flutter_contacts was removed or replaced with a scene-safe fork, '
              'UIScene adoption can be reconsidered — update this test deliberately.');
    });

    test('Crashlytics orientation logging avoids deprecated statusBarOrientation trap', () {
      final podfile = _read('ios/Podfile');
      final crashlyticsNotificationManager = _read(
        'ios/Pods/FirebaseCrashlytics/Crashlytics/Crashlytics/Controllers/FIRCLSNotificationManager.m',
      );

      expect(podfile, contains('patch_firebase_crashlytics_status_bar_orientation'));
      expect(crashlyticsNotificationManager, contains('FIRCLSSafeStatusBarOrientation'));
      expect(
        crashlyticsNotificationManager,
        isNot(contains('[FIRCLSApplicationSharedInstance() statusBarOrientation]')),
        reason: 'iOS 27 traps this deprecated UIApplication API during launch.',
      );
    });

    test('AppDelegate launch path does not force unwrap native launch dependencies', () {
      final source = _read('ios/Runner/AppDelegate.swift');
      final launchBody = RegExp(
        r'didFinishLaunchingWithOptions[\s\S]*?return super\.application',
      ).firstMatch(source)?.group(0);

      expect(launchBody, isNotNull);
      expect(
        launchBody,
        isNot(contains('!.binaryMessenger')),
        reason: 'A nil/racy FlutterViewController must fail open instead of killing the app before Dart starts.',
      );
      expect(
        launchBody,
        isNot(contains('session!')),
        reason: 'Watch session setup must not force unwrap during launch.',
      );
      expect(
        launchBody,
        isNot(contains('registrar(forPlugin: "OmiPhoneCallsPlugin")!')),
        reason: 'Optional plugin registrar must not kill launch.',
      );
    });
  });
}
