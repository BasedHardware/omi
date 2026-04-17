import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/enums.dart';

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get connectedDevice => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubConnectivityProvider extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized or platform channels unavailable
    }
  });

  Future<void> pumpCaptureWidget(WidgetTester tester, CaptureProvider captureProvider) async {
    final deviceProvider = _StubDeviceProvider();
    final connectivityProvider = _StubConnectivityProvider();
    final phoneCallProvider = _StubPhoneCallProvider();
    addTearDown(deviceProvider.dispose);
    addTearDown(connectivityProvider.dispose);
    addTearDown(phoneCallProvider.dispose);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: MultiProvider(
            providers: [
              ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
              ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
              ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
              ChangeNotifierProvider<PhoneCallProvider>.value(value: phoneCallProvider),
            ],
            child: const ConversationCaptureWidget(),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  group('simplified status indicators (#6672)', () {
    testWidgets('shows Listening during phone mic recording when transcription is down', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.record);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      final reconnectText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text(listeningText), findsWidgets);
      expect(find.text(reconnectText), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Listening during initialising state', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingState(RecordingState.initialising);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;

      expect(find.text(listeningText), findsWidgets);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('shows Listening during device recording when transcription is down', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      // Set up a fake recording device to exercise the device recording path
      captureProvider.updateRecordingDevice(
        BtDevice(id: 'test-device', name: 'Test Omi', type: DeviceType.omi, rssi: -50),
      );
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      final reconnectText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text(listeningText), findsWidgets);
      expect(find.text(reconnectText), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });

    testWidgets('paused state overrides Listening during device recording', (tester) async {
      final captureProvider = CaptureProvider();
      addTearDown(captureProvider.dispose);
      captureProvider.updateRecordingDevice(
        BtDevice(id: 'test-device', name: 'Test Omi', type: DeviceType.omi, rssi: -50),
      );
      captureProvider.updateRecordingState(RecordingState.deviceRecord);

      await pumpCaptureWidget(tester, captureProvider);

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;
      final mutedText = AppLocalizations.of(context).muted;

      // Initially should show Listening
      expect(find.text(listeningText), findsWidgets);

      // Simulate device pause: set isPaused and change to pause state
      captureProvider.updateRecordingState(RecordingState.pause);
      // isPaused is set via pauseDeviceRecording which needs BLE — set it directly
      // by triggering the internal pause flow
      try {
        await captureProvider.pauseDeviceRecording();
      } catch (_) {
        // BLE operations fail in test — but isPaused flag is set before the throw
      }
      await tester.pump();

      // Muted/Paused should override Listening for device recording
      expect(find.text(mutedText), findsWidgets);
    });
  });
}
