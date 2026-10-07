import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/wal.dart';

/// Offline Sync lists recordings, not the 75 s / 3 min files capture writes. A customer's day of
/// recording read as dozens of identical rows, and ten "too old" files from one afternoon were ten
/// Delete buttons.

class _Sync extends ChangeNotifier implements SyncProvider {
  _Sync(this.wals);

  final List<Wal> wals;
  final deleted = <Wal>[];

  @override
  SyncState get syncState => const SyncState();
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => wals;
  @override
  Future<void> deleteWal(Wal wal) async {
    deleted.add(wal);
    wals.remove(wal);
    notifyListeners();
  }

  @override
  int get clearableWalsCount => 0;
  @override
  bool get syncCompleted => false;
  @override
  bool get isSyncing => false;
  @override
  int get needsAttentionWalsCount => 0;
  @override
  int get missingWalsInSeconds => 0;
  @override
  bool get isRateLimited => false;
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  List<Wal> get uploadedWals => const [];
  @override
  List<Wal> get pendingLocalTranscriptionWals => const [];
  @override
  List<SyncedConversationPointer> get syncedConversationsPointers => const [];
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// Ten back-to-back 3 minute files the server refused as too old.
List<Wal> _tooOldAfternoon() {
  final start = DateTime.now().subtract(const Duration(days: 41)).millisecondsSinceEpoch ~/ 1000;
  return [
    for (var i = 9; i >= 0; i--)
      Wal(
        timerStart: start + i * 180,
        codec: BleAudioCodec.opus,
        seconds: 180,
        status: WalStatus.outsideRecoveryWindow,
        storage: WalStorage.disk,
        device: 'pendant',
      ),
  ];
}

Future<_Sync> _pump(WidgetTester tester, List<Wal> wals) async {
  final sync = _Sync(wals);
  tester.view.physicalSize = const Size(1170, 4000);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
      ],
      child: const AutoSyncPage(),
    ),
  ));
  await tester.pump();
  return sync;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('one continuous recording is one row with one Delete, not one per file', (tester) async {
    await _pump(tester, _tooOldAfternoon());

    expect(find.text("Too old to sync — Omi can't accept it"), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    expect(find.textContaining('30m'), findsOneWidget, reason: 'ten 3 min files read as one 30 min recording');
  });

  testWidgets("the recording's Delete removes every file it is made of", (tester) async {
    final sync = await _pump(tester, _tooOldAfternoon());

    await tester.tap(find.text('Delete'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.text('Delete').last); // the confirmation
    await tester.pump(const Duration(milliseconds: 500));

    expect(sync.deleted, hasLength(10));
  });

  testWidgets('tapping a recording lists the files behind it', (tester) async {
    final synced = [for (final w in _tooOldAfternoon()) w..status = WalStatus.synced];
    await _pump(tester, synced);

    await tester.tap(find.textContaining('30m'));
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.textContaining('3m'), findsNWidgets(10));
  });
}
