import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

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

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _PhoneSync {
  int getInFlightSeconds() => 0;
  List<dynamic> getSessionUnsyncedWals(int start) => const [];
  Future<void> finalizeCurrentSession() async {}
  Future<void> stampConversationId(int start, String id) async {}
}

class _Wal implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Syncs {
  final phone = _PhoneSync();
}

class _TrackingCaptureProvider extends CaptureProvider {
  _TrackingCaptureProvider()
      : super(
          walService: _Wal(),
          processInProgressConversation: () => Completer<CreateConversationResponse?>().future,
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  var forceProcessingCalls = 0;

  @override
  Future<void> forceProcessingCurrentConversation() async {
    forceProcessingCalls++;
  }
}

class _Harness {
  _Harness({required this.home, required this.capture});
  final HomeProvider home;
  final _TrackingCaptureProvider capture;
}

TranscriptSegment _segment() {
  return TranscriptSegment(
    id: 'seg-1',
    text: 'hello',
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0.0,
    end: 1.0,
    translations: [],
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('Process Now without confirmation lands on the Conversations tab', (tester) async {
    await SharedPreferencesUtil().saveBool('showSummarizeConfirmation', false);
    final harness = await _pumpCapturingPage(tester);

    expect(find.byKey(const Key('process_now_button')), findsOneWidget);
    await _stopFromPage(tester, harness.capture);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(harness.capture.forceProcessingCalls, 1);
    expect(find.text('Finished Conversation?'), findsNothing);
    expect(harness.home.selectedIndex, 1);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('open-capture'), findsOneWidget);
    expect(find.byType(ConversationCapturingPage), findsNothing);
  });

  testWidgets('Process Now with confirmation lands on the Conversations tab', (tester) async {
    await SharedPreferencesUtil().saveBool('showSummarizeConfirmation', true);
    final harness = await _pumpCapturingPage(tester);

    expect(find.byKey(const Key('process_now_button')), findsOneWidget);
    await _stopFromPage(tester, harness.capture);
    await tester.pump();
    tester.takeException();
    await tester.pump(const Duration(milliseconds: 400));
    tester.takeException();

    expect(find.text('Finished Conversation?'), findsOneWidget);
    await tester.tap(find.text('Confirm').last);
    await tester.pump();
    tester.takeException();
    await tester.pump(const Duration(milliseconds: 400));
    tester.takeException();

    expect(harness.capture.forceProcessingCalls, 1);
    expect(harness.home.selectedIndex, 1);
    await tester.pump(const Duration(seconds: 1));
    tester.takeException();
    expect(find.text('open-capture'), findsOneWidget);
    expect(find.byType(ConversationCapturingPage), findsNothing);
  });

  testWidgets('switchHomeToConversationsTab selects the Conversations tab', (tester) async {
    final home = HomeProvider();
    addTearDown(home.dispose);
    await tester.pumpWidget(
      ChangeNotifierProvider<HomeProvider>.value(
        value: home,
        child: MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () => switchHomeToConversationsTab(context),
              child: const Text('go'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('go'));
    await tester.pump();
    expect(home.selectedIndex, 1);
  });

  testWidgets('optimistic processing row renders the skeleton until title and emoji exist', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: CustomScrollView(
            slivers: [
              getProcessingConversationsWidget([
                ServerConversation(
                  id: '0',
                  createdAt: DateTime.utc(2026),
                  structured: Structured('', '', emoji: ''),
                  status: ConversationStatus.processing,
                ),
              ]),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(find.text('Processing'), findsOneWidget);
    expect(find.text('Weekly standup'), findsNothing);
  });
}

Future<void> _stopFromPage(WidgetTester tester, CaptureProvider capture) async {
  final dynamic state = tester.state(find.byType(ConversationCapturingPage));
  await state.debugStopConversation(capture);
}

Future<_Harness> _pumpCapturingPage(WidgetTester tester) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final home = HomeProvider();
  final capture = _TrackingCaptureProvider()..segments = [_segment()];
  addTearDown(home.dispose);
  addTearDown(capture.dispose);

  final device = _StubDeviceProvider();
  final connectivity = _StubConnectivityProvider();
  final usage = UsageProvider();
  addTearDown(device.dispose);
  addTearDown(connectivity.dispose);
  addTearDown(usage.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: MaterialApp(
        navigatorKey: GlobalKey<NavigatorState>(),
        theme: ThemeData.dark(),
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => const ConversationCapturingPage()),
                  );
                },
                child: const Text('open-capture'),
              ),
            ),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('open-capture'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  expect(find.byType(ConversationCapturingPage), findsOneWidget);
  return _Harness(home: home, capture: capture);
}
