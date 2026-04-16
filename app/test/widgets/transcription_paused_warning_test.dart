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

  group('simplified status indicators (#6672)', () {
    testWidgets(
        'shows Listening with recording indicator when transcription service is down during phone mic recording',
        (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      final connectivityProvider = _StubConnectivityProvider();
      final phoneCallProvider = _StubPhoneCallProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);
      addTearDown(connectivityProvider.dispose);
      addTearDown(phoneCallProvider.dispose);
      // Set recording state directly — avoid onConnectionStateChanged which
      // triggers ServiceManager (not available in widget tests).
      captureProvider.updateRecordingState(RecordingState.record);

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
      final reconnectText = AppLocalizations.of(context).transcriptionPaused;

      // Should show "Listening" instead of "Recording, reconnecting"
      expect(find.text(listeningText), findsWidgets);
      // Reconnect-specific UI must be absent
      expect(find.text(reconnectText), findsNothing);
      expect(find.byIcon(Icons.cloud_off), findsNothing);
    });
  });
}
