import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
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

  group('transcription paused warning UI', () {
    testWidgets('shows reconnecting status and indicator in processing capture widget for phone mic', (tester) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      final connectivityProvider = _StubConnectivityProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);
      addTearDown(connectivityProvider.dispose);
      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.pause);

      await _pumpLocalizedApp(
        tester,
        MultiProvider(
          providers: [
            ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
            ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivityProvider),
            ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
          ],
          child: const ConversationCaptureWidget(),
        ),
      );

      final context = tester.element(find.byType(ConversationCaptureWidget));
      final pausedText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text(pausedText), findsWidgets);
      expect(find.byType(ReconnectingStatusIndicator), findsOneWidget);
    });

    testWidgets('shows reconnecting icon and text in conversation capturing app bar when transcript service is down', (
      tester,
    ) async {
      final captureProvider = CaptureProvider();
      final deviceProvider = _StubDeviceProvider();
      addTearDown(captureProvider.dispose);
      addTearDown(deviceProvider.dispose);
      captureProvider.onConnectionStateChanged(true);
      captureProvider.updateRecordingState(RecordingState.record);

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
      final pausedText = AppLocalizations.of(context).transcriptionPaused;

      expect(find.text('🎙️⚡'), findsOneWidget);
      expect(find.text(pausedText), findsOneWidget);
    });
  });
}
