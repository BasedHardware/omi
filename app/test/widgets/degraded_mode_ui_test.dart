import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/phone_call_provider.dart';
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
  });

  Future<void> _pumpLocalizedApp(WidgetTester tester, Widget child) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: child),
      ),
    );
    await tester.pump();
  }

  group('CaptureProvider degraded state lifecycle', () {
    test('stt_degraded event sets isSttDegraded to true', () {
      final provider = CaptureProvider();
      addTearDown(provider.dispose);
      expect(provider.isSttDegraded, isFalse);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG circuit breaker open'),
      );
      expect(provider.isSttDegraded, isTrue);
    });

    test('stt_recovered event clears isSttDegraded', () {
      final provider = CaptureProvider();
      addTearDown(provider.dispose);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG down'),
      );
      expect(provider.isSttDegraded, isTrue);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_recovered', statusText: 'STT Service Restored'),
      );
      expect(provider.isSttDegraded, isFalse);
    });

    test('ready event clears isSttDegraded', () {
      final provider = CaptureProvider();
      addTearDown(provider.dispose);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG down'),
      );
      expect(provider.isSttDegraded, isTrue);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'ready'),
      );
      expect(provider.isSttDegraded, isFalse);
    });

    test('onClosed resets isSttDegraded', () {
      final provider = CaptureProvider();
      addTearDown(provider.dispose);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG down'),
      );
      expect(provider.isSttDegraded, isTrue);

      provider.onClosed();
      expect(provider.isSttDegraded, isFalse);
    });

    test('onError resets isSttDegraded', () {
      final provider = CaptureProvider();
      addTearDown(provider.dispose);

      provider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG down'),
      );
      expect(provider.isSttDegraded, isTrue);

      provider.onError(Exception('test error'));
      expect(provider.isSttDegraded, isFalse);
    });

    test('MessageServiceStatusEvent parses metadata field', () {
      final event = MessageServiceStatusEvent.fromJson({
        'type': 'service_status',
        'status': 'stt_degraded',
        'status_text': 'DG circuit breaker open',
        'metadata': {'batch_mode': true, 'batch_interval_seconds': 30},
      });
      expect(event.metadata, isNotNull);
      expect(event.metadata!['batch_mode'], isTrue);
      expect(event.metadata!['batch_interval_seconds'], 30);
    });

    test('MessageServiceStatusEvent metadata is null when absent', () {
      final event = MessageServiceStatusEvent.fromJson({
        'type': 'service_status',
        'status': 'ready',
      });
      expect(event.metadata, isNull);
    });
  });

  group('ConversationCaptureWidget degraded UI (unified recording UI)', () {
    testWidgets('shows degraded text and amber sync icon when STT is degraded', (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      final connectivityProvider = _StubConnectivityProvider();
      final phoneCallProvider = _StubPhoneCallProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);
      addTearDown(connectivityProvider.dispose);
      addTearDown(phoneCallProvider.dispose);

      // Simulate connected + recording + transcript service ready
      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.record);
      captureProvider.onConnected();
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'ready'),
      );
      // Now enter degraded mode
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG CB open'),
      );

      await _pumpLocalizedApp(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
            ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
            ChangeNotifierProvider<PhoneCallProvider>.value(value: phoneCallProvider),
          ],
          child: const ConversationCaptureWidget(),
        ),
      );

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final degradedText = AppLocalizations.of(context).transcriptionDegraded;

      // Unified recording UI shows degraded status text inline with amber sync icon
      expect(find.text(degradedText), findsWidgets);
      expect(find.byIcon(Icons.sync), findsOneWidget);
    });

    testWidgets('shows listening text after recovery from degraded', (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      final connectivityProvider = _StubConnectivityProvider();
      final phoneCallProvider = _StubPhoneCallProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);
      addTearDown(connectivityProvider.dispose);
      addTearDown(phoneCallProvider.dispose);

      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.record);
      captureProvider.onConnected();
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'ready'),
      );
      // Enter then recover
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG CB open'),
      );
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_recovered', statusText: 'STT Service Restored'),
      );

      await _pumpLocalizedApp(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
            ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
            ChangeNotifierProvider<PhoneCallProvider>.value(value: phoneCallProvider),
          ],
          child: const ConversationCaptureWidget(),
        ),
      );

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final listeningText = AppLocalizations.of(context).listening;

      // After recovery the unified UI shows Listening text, no sync icon
      expect(find.text(listeningText), findsWidgets);
      expect(find.byIcon(Icons.sync), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });
  });

  group('ConversationCapturingPage degraded UI', () {
    testWidgets('shows degraded emoji and text when STT is degraded', (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);

      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.record);
      captureProvider.onConnected();
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'ready'),
      );
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG CB open'),
      );

      await _pumpLocalizedApp(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
          ],
          child: const ConversationCapturingPage(),
        ),
      );

      final context = tester.element(find.byType(ConversationCapturingPage));
      final degradedText = AppLocalizations.of(context).transcriptionDegraded;

      expect(find.text('🎙️⚠️'), findsOneWidget);
      expect(find.text(degradedText), findsOneWidget);
    });

    testWidgets('reverts to listening after recovery', (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);

      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.record);
      captureProvider.onConnected();
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'ready'),
      );
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_degraded', statusText: 'DG CB open'),
      );
      captureProvider.onMessageEventReceived(
        MessageServiceStatusEvent(status: 'stt_recovered', statusText: 'STT Service Restored'),
      );

      await _pumpLocalizedApp(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
          ],
          child: const ConversationCapturingPage(),
        ),
      );

      expect(find.text('🎙️'), findsOneWidget);
      expect(find.text('🎙️⚠️'), findsNothing);
    });
  });
}
