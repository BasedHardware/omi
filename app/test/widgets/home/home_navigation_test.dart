import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/home/home_deep_links.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/home/home_prompt_gate.dart';
import 'package:omi/utils/enums.dart';

/// Home shell navigation: links open inside the one Home (nav #3, #18), prompts wait while the
/// person is busy (onboarding-home #23), and Settings changes are compared after the sheet closes
/// (onboarding-home #25).
void main() {
  group('HomeDeepLink.parse', () {
    test('splits alias, id and query', () {
      final link = HomeDeepLink.parse('/conversation/abc?share=1')!;
      expect(link.alias, 'conversation');
      expect(link.id, 'abc');
      expect(link.query['share'], '1');
    });

    test('accepts a route without a leading slash and ignores empty segments', () {
      final link = HomeDeepLink.parse('apps//xyz')!;
      expect(link.alias, 'apps');
      expect(link.id, 'xyz');
    });

    test('null or empty routes are not links', () {
      expect(HomeDeepLink.parse(null), isNull);
      expect(HomeDeepLink.parse(''), isNull);
      expect(HomeDeepLink.parse('/'), isNull);
    });

    test('selects the parent tab before the page', () {
      expect(HomeDeepLink.parse('/action-items')!.tabIndex, 2);
      expect(HomeDeepLink.parse('/apps/xyz')!.tabIndex, 3);
      expect(HomeDeepLink.parse('/memories')!.tabIndex, 0);
      expect(HomeDeepLink.parse('/conversation/abc')!.tabIndex, isNull);
    });
  });

  group('promptsBlocked', () {
    bool blocked({
      RecordingState recording = RecordingState.stop,
      bool batch = false,
      bool micInterrupted = false,
      PhoneCallState call = PhoneCallState.idle,
      bool firmware = false,
    }) =>
        promptsBlocked(
          recordingState: recording,
          phoneMicBatchRecording: batch,
          micInterruptedByCall: micInterrupted,
          callState: call,
          firmwareUpdateInProgress: firmware,
        );

    test('idle, passive wearable capture and a muted pendant do not hold prompts', () {
      expect(blocked(), isFalse);
      expect(blocked(recording: RecordingState.deviceRecord), isFalse);
      expect(blocked(recording: RecordingState.pause), isFalse);
    });

    test('recording, a call or a firmware update holds prompts', () {
      expect(blocked(recording: RecordingState.record), isTrue);
      expect(blocked(recording: RecordingState.initialising), isTrue);
      expect(blocked(recording: RecordingState.systemAudioRecord), isTrue);
      expect(blocked(batch: true), isTrue);
      expect(blocked(micInterrupted: true), isTrue);
      expect(blocked(call: PhoneCallState.active), isTrue);
      expect(blocked(call: PhoneCallState.ringing), isTrue);
      expect(blocked(firmware: true), isTrue);
    });
  });

  group('HomeNavigation', () {
    tearDown(() {
      // Nothing registered leaks into the next test.
      HomeNavigation.unregister(_record);
    });

    testWidgets('openRoute pops to the existing Home and lets it open the page', (tester) async {
      final navigatorKey = GlobalKey<NavigatorState>();
      await tester.pumpWidget(MaterialApp(navigatorKey: navigatorKey, home: const Text('home')));
      navigatorKey.currentState!.push(MaterialPageRoute<void>(builder: (_) => const Text('conversation')));
      await tester.pumpAndSettle();
      expect(find.text('conversation'), findsOneWidget);

      _opened.clear();
      HomeNavigation.register(_record);
      final opened = await HomeNavigation.openRoute('/chat/omi', navigator: navigatorKey.currentState);
      await tester.pumpAndSettle();

      expect(opened, isTrue);
      expect(_opened, ['/chat/omi']);
      expect(find.text('home'), findsOneWidget);
      expect(find.text('conversation'), findsNothing);
    });

    testWidgets('openRoute drops the link when no Home appears', (tester) async {
      await tester.runAsync(() async {
        final opened = await HomeNavigation.openRoute(
          '/chat/omi',
          timeout: const Duration(milliseconds: 60),
          pollInterval: const Duration(milliseconds: 10),
        );
        expect(opened, isFalse);
      });
    });
  });
}

final List<String> _opened = [];

Future<void> _record(String route) async => _opened.add(route);
