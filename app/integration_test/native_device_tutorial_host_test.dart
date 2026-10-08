import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/utils/other/temp.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Stands in for the capture owner: the tutorial's batch-mode handshake with no BLE or microphone.
class _FakeCapture extends ChangeNotifier implements CaptureProvider {
  @override
  DeviceOnboardingProvider? deviceOnboardingProvider;

  @override
  Future<void> suspendBatchModeForOnboarding() async {}

  @override
  Future<void> restoreBatchModeAfterOnboarding() async {}

  @override
  void cancelTutorialOwnedVoiceSession() {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Simulator-only: flutter drive --driver integration_test/native_ui_host_driver.dart
/// --target integration_test/native_device_tutorial_host_test.dart --flavor dev
/// --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('the device tutorial opened like Device Settings renders natively and close persists completion',
        (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final capture = _FakeCapture();
      await tester.pumpWidget(nativeHostApp(
          Builder(
              builder: (context) => Scaffold(
                  body: Center(
                      child: TextButton(
                          // The same route Device Settings › Device Tutorial pushes.
                          onPressed: () =>
                              routeToPage(context, const InteractiveDeviceOnboardingWrapper(allowExit: true)),
                          child: const Text('device tutorial'))))),
          providers: [ChangeNotifierProvider<CaptureProvider>.value(value: capture)]));
      await tester.tap(find.text('device tutorial'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-device-tutorial-intro-dark');
      expect(nativeProjectedRow(tester, 'device_tutorial_close').symbol, 'xmark');
      await nativeProjectedRow(tester, 'dev_tut_start').action!(null);
      await tester.pump();

      await checkNativeHost(tester, 'native-device-tutorial-transcription-dark');
      expect(nativeProjectedRow(tester, 'device_tutorial_step').value, 1.0);
      final provider = capture.deviceOnboardingProvider!;
      provider.onTranscriptSegments([
        TranscriptSegment(
            id: 'demo',
            text: 'Testing my new Omi right now',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0,
            end: 2,
            translations: []),
      ]);
      await tester.pump(const Duration(seconds: 2));
      await checkNativeHost(tester, 'native-device-tutorial-transcription-done-dark');
      expect(nativeProjectedRow(tester, 'dev_tut_transcript').title, 'Testing my new Omi right now');

      expect(SharedPreferencesUtil().deviceOnboardingCompleted, isFalse);
      await nativeProjectedRow(tester, 'device_tutorial_close').action!(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(SharedPreferencesUtil().deviceOnboardingCompleted, isTrue);
      expect(find.byType(InteractiveDeviceOnboardingWrapper), findsNothing);
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });
}
