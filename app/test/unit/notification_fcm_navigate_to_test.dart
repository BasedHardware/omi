import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/notifications.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('NotificationUtil.navigateToFromFcmData (#5126)', () {
    test('returns navigate_to when it is a non-empty String', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': '/chat/omi'}), '/chat/omi');
    });

    test('returns null when navigate_to is missing', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'type': 'plugin'}), isNull);
    });

    test('returns null when navigate_to is empty', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': ''}), isNull);
    });

    test('returns null when navigate_to is not a String', () {
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': 42}), isNull);
      expect(NotificationUtil.navigateToFromFcmData(const {'navigate_to': true}), isNull);
    });
  });

  group('NotificationUtil.routeFromFcmData (capture recovery)', () {
    test('routes the exact capture_recovery payload to device settings', () {
      expect(
        NotificationUtil.routeFromFcmData(
          const {'push_type': 'capture_recovery', 'action': 'repair_device'},
        ),
        '/settings/device',
      );
    });

    test('capture_recovery ignores a spoofed navigate_to for the route', () {
      expect(
        NotificationUtil.routeFromFcmData(
          const {'push_type': 'capture_recovery', 'action': 'repair_device', 'navigate_to': '/chat/omi'},
        ),
        '/settings/device',
      );
    });

    test('an unknown push_type routes nowhere', () {
      expect(
        NotificationUtil.routeFromFcmData(const {'push_type': 'marketing', 'navigate_to': '/chat/omi'}),
        isNull,
      );
    });

    test('a mismatched capture_recovery action routes nowhere — never falling back to navigate_to', () {
      for (final data in const [
        {'push_type': 'capture_recovery', 'action': 'open_app', 'navigate_to': '/chat/omi'},
        {'push_type': 'capture_recovery', 'navigate_to': '/settings/device'},
      ]) {
        expect(NotificationUtil.routeFromFcmData(data), isNull);
      }
    });

    test('legacy navigate_to without push_type still routes', () {
      expect(NotificationUtil.routeFromFcmData(const {'navigate_to': '/conversation/abc'}), '/conversation/abc');
      expect(NotificationUtil.routeFromFcmData(const {}), isNull);
    });

    test('a non-string push_type is not a typed push and falls back to navigate_to', () {
      expect(
        NotificationUtil.routeFromFcmData(const {'push_type': 42, 'navigate_to': '/chat/omi'}),
        '/chat/omi',
      );
    });
  });

  group('NotificationUtil.handleFcmDataTap', () {
    testWidgets('a capture_recovery tap opens /settings/device in the mounted Home', (tester) async {
      final opened = <String>[];
      final actioned = <Map<String, Object>>[];
      final previousMonitor = CaptureWedgeMonitor.instance;
      CaptureWedgeMonitor.instance = CaptureWedgeMonitor(
        featureGate: () async => true,
        track: (event, properties) {
          if (event == 'Capture Recovery Actioned') actioned.add(properties);
        },
        bleRetry: (_) async {},
        appBuild: () => '1',
        platform: () => 'ios',
      );
      Future<void> opener(String route) async => opened.add(route);
      HomeNavigation.register(opener);
      addTearDown(() {
        HomeNavigation.unregister(opener);
        CaptureWedgeMonitor.instance = previousMonitor;
      });

      await tester.pumpWidget(MaterialApp(
        navigatorKey: globalNavigatorKey,
        home: const Scaffold(body: SizedBox()),
      ));

      final routed = await NotificationUtil.handleFcmDataTap(
        const {'push_type': 'capture_recovery', 'action': 'repair_device'},
      );

      expect(routed, isTrue);
      expect(opened, ['/settings/device']);
      expect(actioned.single['surface'], 'push');
    });

    testWidgets('a mismatched typed payload opens nothing', (tester) async {
      final opened = <String>[];
      Future<void> opener(String route) async => opened.add(route);
      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));

      await tester.pumpWidget(MaterialApp(
        navigatorKey: globalNavigatorKey,
        home: const Scaffold(body: SizedBox()),
      ));

      final routed = await NotificationUtil.handleFcmDataTap(
        const {'push_type': 'capture_recovery', 'action': 'open_app', 'navigate_to': '/chat/omi'},
      );

      expect(routed, isFalse);
      expect(opened, isEmpty);
    });
  });

  group('NotificationUtil.waitUntilNonNull (#5126 cold-start)', () {
    test('returns immediately when value is already present', () async {
      final result = await NotificationUtil.waitUntilNonNull(
        () => 'ready',
        timeout: const Duration(milliseconds: 50),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, 'ready');
    });

    test('resolves once the value appears after a delay', () async {
      String? value;
      Future<void>.delayed(const Duration(milliseconds: 30), () => value = 'ready');

      final result = await NotificationUtil.waitUntilNonNull(
        () => value,
        timeout: const Duration(seconds: 1),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, 'ready');
    });

    test('returns null when the value never appears before timeout', () async {
      final result = await NotificationUtil.waitUntilNonNull<String>(
        () => null,
        timeout: const Duration(milliseconds: 40),
        pollInterval: const Duration(milliseconds: 5),
      );
      expect(result, isNull);
    });
  });
}
