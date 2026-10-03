import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/omi_routes.dart';

// Finish on the live transcript awaits the capture's finish and then pops the page. A swipe back
// during that await pops the route first, but the page stays mounted while it animates out, so a
// pop that lands in that window used to remove Home and leave an empty navigator: a black screen
// (#20369).

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

  List<dynamic> getSessionWals(int start) => const [];
}

class _WalService implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Syncs {
  final phone = _PhoneSync();
}

/// A hermetic capture whose finish resolves when the test says so.
class _ControlledCapture extends CaptureProvider {
  _ControlledCapture(this._finish)
      : super(
          walService: _WalService(),
          connectivity: CaptureConnectivityBoundary(
            initiallyConnected: true,
            changes: const Stream.empty(),
            isConnected: () => true,
          ),
          bleListeners: _NoopBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );

  final Future<void> _finish;

  @override
  Future<void> finishCapture() => _finish;
}

/// Home (a stand-in) as the navigator's only route, with the capturing page pushed on top the way
/// the app pushes it. Returns the capture the page finishes.
Future<CaptureProvider> _pumpHomeWithCapturingPage(
  WidgetTester tester, {
  required HomeProvider home,
  required Future<void> finish,
}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final capture = _ControlledCapture(finish);
  final device = _StubDeviceProvider();
  final connectivity = _StubConnectivityProvider();
  final usage = UsageProvider();
  addTearDown(capture.dispose);
  addTearDown(device.dispose);
  addTearDown(connectivity.dispose);
  addTearDown(usage.dispose);
  addTearDown(home.dispose);

  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider(
          create: (_) => PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []))..people = [],
        ),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
      ],
      child: MaterialApp(
        theme: ThemeData.dark(),
        locale: const Locale('en'),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: Center(child: Text('home'))),
      ),
    ),
  );
  unawaited(
    Navigator.of(
      tester.element(find.text('home')),
    ).push(omiPageRoute(builder: (_) => const ConversationCapturingPage())),
  );
  await tester.pumpAndSettle();
  expect(find.byType(ConversationCapturingPage), findsOneWidget);
  return capture;
}

/// Taps Finish, as the page's button does; the returned future ends when the page is done with it.
Future<void> _finishFromPage(WidgetTester tester, CaptureProvider capture) {
  final dynamic state = tester.state(find.byType(ConversationCapturingPage));
  return state.debugStopConversation(capture) as Future<void>;
}

void main() {
  // The swipe back and its exit transition are the Cupertino route's, so these run as iOS.
  final ios = TargetPlatformVariant.only(TargetPlatform.iOS);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a finish that resolves while the page is swiped away leaves Home on screen', (tester) async {
    final home = HomeProvider()..setIndex(HomeProvider.tasksTab);
    final finish = Completer<void>();
    final capture = await _pumpHomeWithCapturingPage(tester, home: home, finish: finish.future);

    final finishing = _finishFromPage(tester, capture);
    await tester.pump();

    // The swipe back: the route is popped at once, then animates out for about half a second.
    Navigator.of(tester.element(find.byType(ConversationCapturingPage))).pop();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(ConversationCapturingPage), findsOneWidget, reason: 'still mounted, mid-transition');

    finish.complete();
    await finishing;
    await tester.pumpAndSettle();

    // Home is still the navigator's route, and the finish still moved it to the conversations tab.
    expect(find.text('home'), findsOneWidget);
    expect(find.byType(ConversationCapturingPage), findsNothing);
    expect(home.selectedIndex, HomeProvider.homeTab);
  }, variant: ios);

  testWidgets('a finish with no swipe closes the page and shows the conversations tab', (tester) async {
    final home = HomeProvider()..setIndex(HomeProvider.tasksTab);
    final capture = await _pumpHomeWithCapturingPage(tester, home: home, finish: Future<void>.value());

    await _finishFromPage(tester, capture);
    await tester.pumpAndSettle();

    expect(find.text('home'), findsOneWidget);
    expect(find.byType(ConversationCapturingPage), findsNothing);
    expect(home.selectedIndex, HomeProvider.homeTab);
  }, variant: ios);
}
