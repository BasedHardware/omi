import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Customizable Button Actions Preferences & Fallback Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('Default actions match Issue #2825 requirements', () {
      final prefs = SharedPreferencesUtil();

      // Single Press defaults to Ask Question (3)
      expect(prefs.singlePressAction, equals(3));

      // Double Press defaults to Mute/Unmute (1)
      expect(prefs.doublePressAction, equals(1));

      // Triple Press defaults to End Conversation (0)
      expect(prefs.triplePressAction, equals(0));

      // Backward compatibility: doubleTapAction matches doublePressAction
      expect(prefs.doubleTapAction, equals(1));
      expect(prefs.doubleTapPausesMuting, isTrue);
    });

    test('Customizing button actions correctly updates and persists', () {
      final prefs = SharedPreferencesUtil();

      // Customize: Single press -> Mute/Unmute (1)
      prefs.singlePressAction = 1;
      expect(prefs.singlePressAction, equals(1));

      // Customize: Double press -> Star Conversation (2)
      prefs.doublePressAction = 2;
      expect(prefs.doublePressAction, equals(2));
      expect(prefs.doubleTapAction, equals(2));
      expect(prefs.doubleTapPausesMuting, isFalse);

      // Customize: Triple press -> Ask Question (3)
      prefs.triplePressAction = 3;
      expect(prefs.triplePressAction, equals(3));

      // Customize: None / disabled (4)
      prefs.singlePressAction = 4;
      expect(prefs.singlePressAction, equals(4));
    });

    test('Sanitizes illegal or out-of-range action values to defaults', () {
      final prefs = SharedPreferencesUtil();

      // Illegal values: negative or out of bounds (> 4)
      prefs.singlePressAction = 99;
      expect(prefs.singlePressAction, equals(3)); // 回退至默认 3

      prefs.singlePressAction = -1;
      expect(prefs.singlePressAction, equals(3));

      prefs.doublePressAction = 10;
      expect(prefs.doublePressAction, equals(1)); // 回退至默认 1

      prefs.triplePressAction = -5;
      expect(prefs.triplePressAction, equals(0)); // 回退至默认 0
    });

    test('Sanitizes corrupted initial SharedPreferences values', () async {
      SharedPreferences.setMockInitialValues({
        'singlePressAction': 999,
        'doublePressAction': -10,
        'triplePressAction': 42,
      });
      await SharedPreferencesUtil.init();

      final prefs = SharedPreferencesUtil();
      expect(prefs.singlePressAction, equals(3));
      expect(prefs.doublePressAction, equals(1));
      expect(prefs.triplePressAction, equals(0));
    });

    test('Backward compatibility fallback from legacy doubleTapAction', () async {
      // If only doubleTapAction was previously saved
      SharedPreferences.setMockInitialValues({
        'doubleTapAction': 2,
      });
      await SharedPreferencesUtil.init();

      final prefs = SharedPreferencesUtil();
      expect(prefs.doublePressAction, equals(2));
      expect(prefs.doubleTapAction, equals(2));
    });
  });

  group('Firmware Button State Zero-Copy Unpacking Tests', () {
    test('Unpacks buttonState correctly from BLE notification bytes', () {
      // Helper matching CaptureController sublistView unpacking
      int unpackButtonState(List<int> bytes) {
        return ByteData.sublistView(Uint8List.fromList(bytes)).getUint32(0, Endian.little);
      }

      // Firmware sends: final_button_state[0] as uint32 little endian
      // State 1: SINGLE_TAP
      expect(unpackButtonState([1, 0, 0, 0]), equals(1));

      // State 2: DOUBLE_TAP
      expect(unpackButtonState([2, 0, 0, 0]), equals(2));

      // State 6: TRIPLE_TAP (Issue #2825)
      expect(unpackButtonState([6, 0, 0, 0]), equals(6));

      // State 3: LONG_TAP / POWER OFF
      expect(unpackButtonState([3, 0, 0, 0]), equals(3));

      // State 5: RELEASE
      expect(unpackButtonState([5, 0, 0, 0]), equals(5));
    });

    test('Zero-copy little endian matches legacy reversed buffer unpacking', () {
      final samplePayloads = [
        [1, 0, 0, 0],
        [2, 0, 0, 0],
        [3, 0, 0, 0],
        [5, 0, 0, 0],
        [6, 0, 0, 0],
      ];

      for (final payload in samplePayloads) {
        final legacyUnpack = ByteData.view(
          Uint8List.fromList(payload.sublist(0, 4).reversed.toList()).buffer,
        ).getUint32(0);

        final optimizedUnpack = ByteData.sublistView(
          Uint8List.fromList(payload),
        ).getUint32(0, Endian.little);

        expect(optimizedUnpack, equals(legacyUnpack));
      }
    });
  });

  group('Button Action Routing Logic Tests', () {
    (int action, String eventType)? resolveTapAction(int buttonState, SharedPreferencesUtil prefs) {
      return switch (buttonState) {
        1 => (prefs.singlePressAction, 'single_press'),
        2 => (prefs.doublePressAction, 'double_press'),
        6 => (prefs.triplePressAction, 'triple_press'),
        _ => null,
      };
    }

    test('Routes tap states to configured preferences', () {
      final prefs = SharedPreferencesUtil();
      prefs.singlePressAction = 3;
      prefs.doublePressAction = 1;
      prefs.triplePressAction = 0;

      expect(resolveTapAction(1, prefs), equals((3, 'single_press')));
      expect(resolveTapAction(2, prefs), equals((1, 'double_press')));
      expect(resolveTapAction(6, prefs), equals((0, 'triple_press')));

      // Non-tap or unconfigured states (e.g. 0, 3 long press, 4, 5 release)
      expect(resolveTapAction(0, prefs), isNull);
      expect(resolveTapAction(3, prefs), isNull);
      expect(resolveTapAction(4, prefs), isNull);
      expect(resolveTapAction(5, prefs), isNull);
    });

    test('Customized preferences dynamically redirect button routing', () {
      final prefs = SharedPreferencesUtil();
      prefs.singlePressAction = 1; // Mute
      prefs.doublePressAction = 2; // Star
      prefs.triplePressAction = 4; // Disabled

      expect(resolveTapAction(1, prefs), equals((1, 'single_press')));
      expect(resolveTapAction(2, prefs), equals((2, 'double_press')));
      expect(resolveTapAction(6, prefs), equals((4, 'triple_press')));
    });
  });

  group('In-Flight Conversation Processing & Debounce Tests', () {
    test('Repeated force-processing requests are blocked while processing is in-flight', () async {
      bool isForceProcessing = false;
      int executeCount = 0;

      Future<void> simulateForceProcessing() async {
        if (isForceProcessing) return;
        isForceProcessing = true;
        try {
          executeCount++;
          await Future.delayed(const Duration(milliseconds: 50));
        } finally {
          isForceProcessing = false;
        }
      }

      // Fire first request and immediate concurrent second request
      final f1 = simulateForceProcessing();
      final f2 = simulateForceProcessing();
      await Future.wait([f1, f2]);

      expect(executeCount, equals(1));

      // After in-flight completes, next request is admitted
      await simulateForceProcessing();
      expect(executeCount, equals(2));
    });

    test('Button actions within debounce duration are ignored', () {
      DateTime? lastActionTime;
      const debounce = Duration(milliseconds: 400);
      int firedCount = 0;

      bool triggerButtonAction(DateTime now) {
        if (lastActionTime != null && now.difference(lastActionTime!) < debounce) {
          return false;
        }
        lastActionTime = now;
        firedCount++;
        return true;
      }

      final start = DateTime(2026, 9, 20, 12, 0, 0);
      expect(triggerButtonAction(start), isTrue);
      expect(firedCount, equals(1));

      // Fast second press at +200ms -> ignored
      expect(triggerButtonAction(start.add(const Duration(milliseconds: 200))), isFalse);
      expect(firedCount, equals(1));

      // Third press at +401ms -> accepted
      expect(triggerButtonAction(start.add(const Duration(milliseconds: 401))), isTrue);
      expect(firedCount, equals(2));
    });

    test(
      'Second End/Process press after 400ms debounce while backend is still processing is blocked by in-flight guard',
      () async {
        DateTime? lastActionTime;
        const debounce = Duration(milliseconds: 400);
        bool isForceProcessing = false;
        int backendProcessingChainStarted = 0;
        final sentinelProcessingIds = <String>[];

        Future<bool> handleButtonPress(DateTime now, {required Future<void> Function() backendWork}) async {
          // 1. Debounce check
          if (lastActionTime != null && now.difference(lastActionTime!) < debounce) {
            return false;
          }
          lastActionTime = now;

          // 2. In-flight force-processing reentrancy guard
          if (isForceProcessing) {
            return false;
          }
          isForceProcessing = true;

          try {
            sentinelProcessingIds.add('0');
            backendProcessingChainStarted++;
            await backendWork();
          } finally {
            sentinelProcessingIds.remove('0');
            isForceProcessing = false;
          }
          return true;
        }

        final start = DateTime(2026, 9, 20, 12, 0, 0);
        final completer = Completer<void>();

        // Press 1 at t=0ms: starts long-running backend processing
        final press1Future = handleButtonPress(start, backendWork: () => completer.future);

        // Press 2 at t=200ms: blocked by 400ms debounce
        final press2Result = await handleButtonPress(
          start.add(const Duration(milliseconds: 200)),
          backendWork: () async {},
        );
        expect(press2Result, isFalse);
        expect(backendProcessingChainStarted, equals(1));
        expect(sentinelProcessingIds, equals(['0']));

        // Press 3 at t=450ms: passes debounce (>400ms), but backend is STILL processing -> blocked by in-flight guard
        final press3Result = await handleButtonPress(
          start.add(const Duration(milliseconds: 450)),
          backendWork: () async {},
        );
        expect(press3Result, isFalse);
        expect(backendProcessingChainStarted, equals(1), reason: 'Must not start duplicate backend chain');
        expect(sentinelProcessingIds.length, equals(1), reason: 'Must not add duplicate sentinel processing id 0');

        // Finish backend work
        completer.complete();
        await press1Future;
        expect(sentinelProcessingIds, isEmpty);

        // Press 4 at t=700ms: backend complete, but within 400ms debounce of press 3 (700-450=250ms) -> still blocked by debounce
        final press4Result = await handleButtonPress(
          start.add(const Duration(milliseconds: 700)),
          backendWork: () async {},
        );
        expect(press4Result, isFalse);
        expect(backendProcessingChainStarted, equals(1));

        // Press 5 at t=900ms: backend complete and debounce expired (900-450=450ms > 400ms) -> properly admitted
        final press5Result = await handleButtonPress(
          start.add(const Duration(milliseconds: 900)),
          backendWork: () async {},
        );
        expect(press5Result, isTrue);
        expect(backendProcessingChainStarted, equals(2));
      },
    );
  });
}
