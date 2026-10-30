// Dispatch tests for customizable Omi button actions (#2825), driven through
// handleButtonEventForTesting as requested in review.
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

class _NoSocketCaptureProvider extends CaptureProvider {
  _NoSocketCaptureProvider({
    super.now,
    super.speakerHaptic,
  });

  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
    Geolocation? geolocation,
    bool localPreview = false,
  }) async {
    // Tests must never open a real transcription socket: connecting would hit
    // buildHeaders → AuthService.isSignedIn → FirebaseAuth, none of which are
    // testable without platform plugins.
    return null;
  }
}

BtDevice _device(DeviceType type) => BtDevice(name: 'test-device', id: 'test-id', type: type, rssi: -40);

var now = DateTime.utc(2026, 10, 29, 12);
void advance(Duration d) => now = now.add(d);

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => Directory.systemTemp.path,
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/package_info'),
      (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'},
    );
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env._instance is late final — ignore if already initialized in this isolate.
    }
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialized by another test in this isolate.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'test-device-hash'});
    await SharedPreferencesUtil.init();
    // buildHeaders reads PlatformManager.deviceIdHash, a late field set only
    // by initializeServices() (needs real device plugins). The short-circuit
    // in _getDeviceIdHash() lets us initialize that field from the stored
    // value instead.
    await PlatformManager.initializeServices();
    now = DateTime.utc(2026, 10, 29, 12);
  });

  _NoSocketCaptureProvider makeProvider() {
    final provider = _NoSocketCaptureProvider(now: () => now, speakerHaptic: (_, __) async => true);
    provider.updateRecordingDevice(_device(DeviceType.omi));
    return provider;
  }

  group('default mapping is preserved', () {
    test('defaults: single = Ask Question, double = End & Process, triple = None', () {
      expect(SharedPreferencesUtil().singlePressAction, 3);
      expect(SharedPreferencesUtil().doublePressAction, 0);
      expect(SharedPreferencesUtil().triplePressAction, 4);
    });

    test('single press toggles a voice question on and off (pre-change behavior)', () {
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 1);
      expect(provider.hasVoiceCommandSessionForTesting, isTrue);
      advance(const Duration(seconds: 1));
      provider.handleButtonEventForTesting('test-id', 1);
      expect(provider.hasVoiceCommandSessionForTesting, isFalse);
      provider.dispose();
    });

    test('triple press does nothing by default', () {
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 6);
      expect(provider.hasVoiceCommandSessionForTesting, isFalse);
      expect(provider.isConversationMarkedForStarring, isFalse);
      provider.dispose();
    });

    test('legacy doubleTapAction value still drives double press', () {
      SharedPreferencesUtil().doubleTapAction = 2; // star
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 2);
      expect(provider.isConversationMarkedForStarring, isTrue);
      provider.dispose();
    });
  });

  group('remapped actions route by button state', () {
    test('double -> Ask Question, triple -> Star', () {
      SharedPreferencesUtil().doublePressAction = 3;
      SharedPreferencesUtil().triplePressAction = 2;
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 6);
      expect(provider.isConversationMarkedForStarring, isTrue);
      expect(provider.hasVoiceCommandSessionForTesting, isFalse);
      advance(const Duration(seconds: 1));
      provider.handleButtonEventForTesting('test-id', 2);
      expect(provider.hasVoiceCommandSessionForTesting, isTrue);
      provider.dispose();
    });

    test('single mapped to None does not start a question', () {
      SharedPreferencesUtil().singlePressAction = 4;
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 1);
      expect(provider.hasVoiceCommandSessionForTesting, isFalse);
      provider.dispose();
    });
  });

  group('debounce', () {
    test('a duplicate of the same press type inside the debounce is dropped', () {
      SharedPreferencesUtil().doublePressAction = 2; // star toggles, so a second run would unstar
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 2);
      advance(CaptureController.buttonActionDebounce - const Duration(milliseconds: 1));
      provider.handleButtonEventForTesting('test-id', 2);
      expect(provider.isConversationMarkedForStarring, isTrue);
      provider.dispose();
    });

    test('the next distinct same-type press the firmware can emit is not dropped', () {
      SharedPreferencesUtil().doublePressAction = 2;
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 2);
      advance(CaptureController.firmwareMultiTapWindow);
      provider.handleButtonEventForTesting('test-id', 2);
      expect(provider.isConversationMarkedForStarring, isFalse);
      provider.dispose();
    });

    test('a different press type right after another is not debounced', () {
      SharedPreferencesUtil().singlePressAction = 2; // star
      SharedPreferencesUtil().triplePressAction = 3; // ask
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 1);
      advance(const Duration(milliseconds: 50));
      provider.handleButtonEventForTesting('test-id', 6);
      expect(provider.isConversationMarkedForStarring, isTrue);
      expect(provider.hasVoiceCommandSessionForTesting, isTrue);
      provider.dispose();
    });

    test('ending an active voice question is never debounced', () {
      final provider = makeProvider();
      provider.handleButtonEventForTesting('test-id', 1);
      advance(const Duration(milliseconds: 10));
      provider.handleButtonEventForTesting('test-id', 1);
      expect(provider.hasVoiceCommandSessionForTesting, isFalse);
      provider.dispose();
    });

    test('debounce stays below the shortest gap between distinct firmware presses', () {
      const window = CaptureController.firmwareMultiTapWindow;
      const poll = CaptureController.firmwareButtonPollInterval;
      expect(window, const Duration(milliseconds: 350));
      expect(CaptureController.buttonActionDebounce < window, isTrue);
      // Three taps need at least three press ticks and three release ticks.
      expect(CaptureController.buttonActionDebounce < poll * 6, isTrue);
    });
  });

  group('onboarding', () {
    test('ask-question step forces Ask Question even when single press is remapped', () {
      SharedPreferencesUtil().singlePressAction = 2; // star
      final onboarding = DeviceOnboardingProvider()..startOnboarding();
      onboarding.goToStep(DeviceOnboardingProvider.askQuestionStep);
      final provider = makeProvider();
      provider.deviceOnboardingProvider = onboarding;
      provider.handleButtonEventForTesting('test-id', 1);
      expect(provider.hasVoiceCommandSessionForTesting, isTrue);
      expect(provider.isConversationMarkedForStarring, isFalse);
      provider.dispose();
      onboarding.dispose();
    });

    test('ask-question step ignores double and triple presses', () {
      SharedPreferencesUtil().doublePressAction = 2;
      SharedPreferencesUtil().triplePressAction = 2;
      final onboarding = DeviceOnboardingProvider()..startOnboarding();
      onboarding.goToStep(DeviceOnboardingProvider.askQuestionStep);
      final provider = makeProvider();
      provider.deviceOnboardingProvider = onboarding;
      provider.handleButtonEventForTesting('test-id', 2);
      provider.handleButtonEventForTesting('test-id', 6);
      expect(provider.isConversationMarkedForStarring, isFalse);
      provider.dispose();
      onboarding.dispose();
    });
  });

  group('triple press capability gate', () {
    test('only firmware advertising OmiFeatures.tripleTap offers Triple Press', () {
      const currentFirmware = OmiFeatures.button | OmiFeatures.ledDimming | OmiFeatures.micGain;
      expect(OmiFeatures.supportsTriplePress(currentFirmware), isFalse);
      expect(OmiFeatures.supportsTriplePress(0), isFalse);
      expect(OmiFeatures.supportsTriplePress(currentFirmware | OmiFeatures.tripleTap), isTrue);
    });

    test('app constants match the firmware sources', () {
      final features = File('../omi/firmware/omi/src/lib/core/features.h');
      final transport = File('../omi/firmware/omi/src/lib/core/transport.c');
      final buttons = [
        File('../omi/firmware/omi/src/lib/core/button.c'),
        File('../omi/firmware/devkit/src/button.c'),
      ];
      if (!features.existsSync()) {
        // App-only checkout: nothing to compare against.
        return;
      }
      expect(features.readAsStringSync(), contains('OMI_FEATURE_TRIPLE_TAP = (1 << 9)'));
      expect(OmiFeatures.tripleTap, 1 << 9);
      expect(transport.readAsStringSync(), contains('features |= OMI_FEATURE_TRIPLE_TAP;'));
      for (final f in buttons) {
        final src = f.readAsStringSync();
        expect(src, contains('#define MULTI_TAP_WINDOW_MS ${CaptureController.firmwareMultiTapWindow.inMilliseconds}'),
            reason: f.path);
        expect(src,
            contains('#define BUTTON_CHECK_INTERVAL ${CaptureController.firmwareButtonPollInterval.inMilliseconds}'),
            reason: f.path);
      }
    });
  });
}
