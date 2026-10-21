import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  BtDevice? get pairedDevice => null;
  @override
  BtDevice? get connectedDevice => null;
  @override
  bool get isConnected => false;
  @override
  bool get isConnecting => false;
  @override
  int get batteryLevel => 0;
  @override
  bool get isCharging => false;
  @override
  bool get havingNewFirmware => false;
  @override
  Future<void> getDeviceInfo() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get isPaused => false;
  @override
  bool get havingRecordingDevice => false;
  @override
  BtDevice? get recordingDevice => null;
  @override
  String? get liveCaptureSource => null;
  @override
  List<TranscriptSegment> get segments => const [];
  @override
  void addMetricsListener() {}
  @override
  void removeMetricsListener() {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Sync extends ChangeNotifier implements SyncProvider {
  _Sync({this.wals = const [], this.state = const SyncState()});
  List<Wal> wals;
  SyncState state;
  @override
  SyncState get syncState => state;
  @override
  bool get isSyncing => state.isSyncing;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  bool get isRateLimited => false;
  @override
  int get missingWalsInSeconds => wals.fold(0, (v, w) => v + w.seconds);
  void update(List<Wal> next) {
    wals = next;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _start = DateTime(2026, 10, 20, 11);
Wal _wal({int minutes = 180, WalStatus status = WalStatus.miss}) => Wal(
    timerStart: _start.millisecondsSinceEpoch ~/ 1000,
    codec: BleAudioCodec.opus,
    seconds: minutes * 60,
    status: status,
    storage: WalStorage.sdcard,
    device: 'omi');

void main() {
  Future<PendingWorkStore> pump(WidgetTester tester, _Sync sync,
      {List<PendingWorkItem> pending = const [], List<ServerConversation> conversations = const []}) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, items: pending, attentionUnseenCount: 0)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    final device = _Device();
    final capture = _Capture();
    final conversationProvider = ConversationProvider(isSignedIn: () => false)..conversations = conversations;
    final home = HomeProvider();
    addTearDown(store.dispose);
    addTearDown(device.dispose);
    addTearDown(capture.dispose);
    addTearDown(conversationProvider.dispose);
    addTearDown(home.dispose);
    addTearDown(sync.dispose);
    tester.view.physicalSize = const Size(390, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>.value(value: device),
          ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ChangeNotifierProvider<SyncProvider>.value(value: sync),
          ChangeNotifierProvider<ConversationProvider>.value(value: conversationProvider),
          ChangeNotifierProvider<HomeProvider>.value(value: home),
        ],
        child: MaterialApp(
            theme: buildOmiTheme(),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: DeviceSettings(pendingWork: store))));
    await tester.pump();
    return store;
  }

  testWidgets('large idle backlog has progress, audio span and reachable On the Way', (tester) async {
    await pump(tester, _Sync(wals: [_wal()]));
    expect(find.text('Catching up'), findsOneWidget);
    expect(find.text('0 of 180 min'), findsOneWidget);
    expect(find.byKey(const Key('device_catching_up_span')), findsOneWidget);
    expect(tester.widget<Text>(find.byKey(const Key('device_catching_up_span'))).data, contains('11'));
    expect(find.byKey(const Key('device_catching_up_targets')), findsNothing);
    await tester.tap(find.byKey(const Key('device_catching_up_on_the_way')));
    await tester.pumpAndSettle();
    expect(find.byType(OnTheWayPage), findsOneWidget);
    expect(find.text('All recordings are synced'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final ids in <List<String>>[
    [],
    ['a', 'b']
  ]) {
    testWidgets('server-only catch-up stays visible for targets=$ids and opens its work', (tester) async {
      final item = PendingWorkItem(
          id: 'sync:j',
          kind: 'sync_job',
          state: 'transcribing',
          conversationIds: ids,
          startedAt: _start,
          durationSeconds: 720);
      final pending = [item];
      final store = await pump(tester, _Sync(), pending: pending, conversations: [
        for (final id in ids)
          ServerConversation(
              id: id,
              createdAt: _start,
              structured: Structured('Conversation $id', ''),
              status: ConversationStatus.completed),
      ]);
      await store.refresh();
      await tester.pump();
      expect(find.text('Catching up'), findsOneWidget);
      expect(find.text('Processing'), findsOneWidget);
      expect(tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).value, isNull);
      expect(find.byKey(const Key('device_catching_up_span')), findsOneWidget);
      if (ids.isNotEmpty) expect(find.text('2 conversations · Conversation a · Conversation b'), findsOneWidget);
      await tester.tap(find.byKey(const Key('device_catching_up_on_the_way')));
      await tester.pumpAndSettle();
      expect(find.byType(OnTheWayPage), findsOneWidget);
      expect(find.text('All recordings are synced'), findsNothing);
      await tester.pageBack();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      pending.clear();
      await store.refresh();
      await tester.pump();
      expect(find.text('Catching up'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('catch-up clears when local work finishes; terminal failures do not masquerade as progress',
      (tester) async {
    final sync = _Sync(wals: [_wal()]);
    await pump(tester, sync);
    expect(find.text('Catching up'), findsOneWidget);
    sync.update([_wal(status: WalStatus.synced)]);
    await tester.pump();
    expect(find.text('Catching up'), findsNothing);
    sync.update([_wal()..retryCount = 99]);
    await tester.pump();
    expect(find.text('Catching up'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a synced phone twin hides the card instead of opening an empty page', (tester) async {
    final phone = _wal(minutes: 4, status: WalStatus.synced)..storage = WalStorage.disk;
    final deviceTwin = _wal(minutes: 4);
    await pump(tester, _Sync(wals: [phone, deviceTwin]));
    expect(find.text('Catching up'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a synced first chunk keeps the card on its longer device source', (tester) async {
    final chunk = _wal(minutes: 1, status: WalStatus.synced)..storage = WalStorage.disk;
    final source = _wal(minutes: 4);
    await pump(tester, _Sync(wals: [chunk, source]));
    expect(find.text('Catching up'), findsOneWidget);
    expect(find.text('0 of 4 min'), findsOneWidget);
    await tester.tap(find.byKey(const Key('device_catching_up_on_the_way')));
    await tester.pumpAndSettle();
    expect(find.text('All recordings are synced'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('phone-only waiting audio is measured instead of Processing', (tester) async {
    final phone = _wal(minutes: 180)..storage = WalStorage.disk;
    await pump(tester, _Sync(wals: [phone]));
    expect(find.text('Catching up'), findsOneWidget);
    expect(find.text('180 of 180 min'), findsOneWidget);
    expect(tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).value, 1.0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('retry-exhausted audio does not count toward the progress total', (tester) async {
    final failed = _wal(minutes: 180)
      ..retryCount = 99
      ..timerStart += 60;
    final waiting = _wal(minutes: 1);
    await pump(tester, _Sync(wals: [failed, waiting]));
    expect(find.text('Catching up'), findsOneWidget);
    expect(find.text('0 of 1 min'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('card wraps at 200 percent text scale', (tester) async {
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: MediaQuery(
          data: const MediaQueryData(size: Size(320, 844), textScaler: TextScaler.linear(2)),
          child: Scaffold(
              body: SizedBox(
                  width: 320,
                  child: SingleChildScrollView(
                      child: DeviceCatchingUpCard(
                    summary: const DeviceCatchUpSummary(
                        progress: (doneSeconds: 240, totalSeconds: 10800),
                        targetIds: {'a', 'b'},
                        targetTitles: ['A very long conversation title', 'Another conversation']),
                    onOpen: () {},
                  )))),
        )));
    expect(tester.takeException(), isNull);
    final semantics = tester.ensureSemantics();
    expect(tester.getSemantics(find.byKey(const Key('device_catching_up_on_the_way'))).label, 'On the Way');
    semantics.dispose();
  });

  testWidgets('a WAL-less server phase remains reachable', (tester) async {
    await pump(tester, _Sync(state: const SyncState(status: SyncStatus.fetchingConversations)));
    expect(find.text('Catching up'), findsOneWidget);
    expect(find.byKey(const Key('device_catching_up_on_the_way')), findsOneWidget);
    await tester.tap(find.byKey(const Key('device_catching_up_on_the_way')));
    await tester.pumpAndSettle();
    expect(find.byType(OnTheWayPage), findsOneWidget);
    expect(find.text('All recordings are synced'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
