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
import 'package:omi/pages/settings/device/device_live_sections.dart';
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
  bool get isSyncStalled => false; // The watchdog's stall (#15501) is not under test here.
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
  bool get pendantCaptureActionRequired => false;
  @override
  bool get pendantCaptureVerified => true;
  @override
  bool get pendantReconnectInFlight => false;
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
  DateTime? get liveCaptureStartedAt => null;
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

/// A pendant recording stamped before the device clock was ever set.
final _unsetClockStart = DateTime(1985, 9, 5, 16, 17);
Wal _unsetClockWal({int minutes = 1}) => Wal(
    timerStart: _unsetClockStart.millisecondsSinceEpoch ~/ 1000,
    codec: BleAudioCodec.opus,
    seconds: minutes * 60,
    status: WalStatus.miss,
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

  final tile = find.byKey(const Key('device_stat_catching_up'));
  String tileValue(WidgetTester tester) =>
      tester.widget<Text>(find.descendant(of: tile, matching: find.byType(Text)).at(1)).data!;

  /// Option C: no stage words, date ranges or conversation titles anywhere on the device page.
  void expectQuiet() {
    expect(find.text('Waiting to sync'), findsNothing);
    expect(find.text('Processing'), findsNothing);
    expect(find.text('Transcribing…'), findsNothing);
    expect(find.byKey(const Key('device_catching_up_span')), findsNothing);
    expect(find.byKey(const Key('device_catching_up_targets')), findsNothing);
    expect(find.textContaining('Conversation '), findsNothing);
  }

  testWidgets('a large idle backlog is the Catching up tile, and the tile opens On the Way', (tester) async {
    await pump(tester, _Sync(wals: [_wal()]));
    expect(tile, findsOneWidget);
    expect(find.byKey(const Key('device_stat_on_device')), findsNothing);
    expect(tileValue(tester), '3h');
    expect(find.descendant(of: tile, matching: find.textContaining('on its way')), findsOneWidget);
    expect(find.byKey(const Key('device_right_now_catching_up')), findsNothing,
        reason: 'Right now keeps only Listening');
    expect(find.byType(LinearProgressIndicator), findsNothing);
    expectQuiet();
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(find.byType(OnTheWayPage), findsOneWidget);
    expect(find.text('All recordings are synced'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final ids in <List<String>>[
    [],
    ['a', 'b']
  ]) {
    testWidgets('server-only catch-up stays on the tile for targets=$ids and opens its work', (tester) async {
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
      expect(tile, findsOneWidget);
      expect(tileValue(tester), '12m');
      expectQuiet();
      await tester.tap(tile);
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

  testWidgets('a never-set device clock still counts its audio but never names 1985', (tester) async {
    await pump(tester, _Sync(wals: [_unsetClockWal(), _wal(minutes: 180)]));
    expect(tileValue(tester), '3h 1m');
    expect(find.textContaining('1985'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a never-set clock recording alone keeps the tile', (tester) async {
    await pump(tester, _Sync(wals: [_unsetClockWal()]));
    expect(tileValue(tester), '1m');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('server work stamped before 2024 keeps its tile with no title or date', (tester) async {
    final item = PendingWorkItem(
        id: 'sync:j',
        kind: 'sync_job',
        state: 'transcribing',
        conversationIds: ['a'],
        startedAt: _unsetClockStart,
        durationSeconds: 720);
    final store = await pump(tester, _Sync(), pending: [
      item
    ], conversations: [
      ServerConversation(
          id: 'a',
          createdAt: _unsetClockStart,
          structured: Structured('Before its clock was set', ''),
          status: ConversationStatus.completed),
    ]);
    await store.refresh();
    await tester.pump();
    expect(tileValue(tester), '12m');
    expect(find.text('Before its clock was set'), findsNothing);
    expect(find.textContaining('1985'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

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

  testWidgets('a synced phone twin hides the tile instead of opening an empty page', (tester) async {
    final phone = _wal(minutes: 4, status: WalStatus.synced)..storage = WalStorage.disk;
    final deviceTwin = _wal(minutes: 4);
    await pump(tester, _Sync(wals: [phone, deviceTwin]));
    expect(find.text('Catching up'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('phone-only waiting audio is a duration, with no stage word or bar', (tester) async {
    final phone = _wal(minutes: 180)..storage = WalStorage.disk;
    await pump(tester, _Sync(wals: [phone]));
    expect(tileValue(tester), '3h');
    expectQuiet();
    expect(find.byType(LinearProgressIndicator), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a fully synced chunk drain hides its lagging source', (tester) async {
    final first = _wal(minutes: 2, status: WalStatus.synced)
      ..storage = WalStorage.disk
      ..originalStorage = WalStorage.sdcard;
    final second = _wal(minutes: 1, status: WalStatus.synced)
      ..storage = WalStorage.disk
      ..originalStorage = WalStorage.sdcard
      ..timerStart += 120;
    final source = _wal(minutes: 3);
    await pump(tester, _Sync(wals: [first, second, source]));
    expect(find.text('Catching up'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('retry-exhausted audio never holds the tile on its own', (tester) async {
    final failed = _wal(minutes: 180)
      ..retryCount = 99
      ..timerStart += 60;
    final waiting = _wal(minutes: 1);
    final sync = _Sync(wals: [failed, waiting]);
    await pump(tester, sync);
    expect(tileValue(tester), '1m', reason: 'the exhausted recording is not counted as on its way');
    sync.update([failed]);
    await tester.pump();
    expect(find.text('Catching up'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('the tile wraps at 200 percent text scale', (tester) async {
    var opened = 0;
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: MediaQuery(
          data: const MediaQueryData(size: Size(320, 844), textScaler: TextScaler.linear(2)),
          child: Scaffold(
              body: SizedBox(
                  width: 320,
                  child: SingleChildScrollView(
                      child: DeviceStatsRow(
                    batteryLevel: 72,
                    isCharging: true,
                    heardTodaySeconds: 33 * 60,
                    onDeviceSeconds: 0,
                    catchUpSeconds: 8 * 3600 + 14 * 60,
                    catchUpCaption: 'when online',
                    onOpenCatchUp: () => opened++,
                  )))),
        )));
    expect(tester.takeException(), isNull);
    final semantics = tester.ensureSemantics();
    expect(tester.getSemantics(tile).label, 'Catching up, 8h 14m, when online');
    expect(tester.getSemantics(tile).flagsCollection.isButton, isTrue);
    expect(tester.getSize(tile).height, greaterThanOrEqualTo(44));
    semantics.dispose();
    await tester.tap(tile);
    expect(opened, 1);
  });

  testWidgets('a WAL-less server phase remains reachable', (tester) async {
    await pump(tester, _Sync(state: const SyncState(status: SyncStatus.fetchingConversations)));
    expect(tile, findsOneWidget);
    expect(tileValue(tester), '—', reason: 'pending but not yet measured');
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(find.byType(OnTheWayPage), findsOneWidget);
    expect(find.text('All recordings are synced'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
