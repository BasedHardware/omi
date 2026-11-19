import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:omi/env/env.dart';
import 'package:omi/ui/ui.dart';
import '../../helpers/sfpro_font_fixtures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/sync_job_cancel.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/server_cancel_pause.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_sync_views.dart';

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String? get intercomAppId => 'synthetic-support';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

final _boundary = GlobalKey();
const _output = String.fromEnvironment('OFFLINE_SYNC_RENDER_OUTPUT');

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

Future<void> _frame(WidgetTester tester, String name) async {
  expect(tester.takeException(), isNull);
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
  });
}

/// Offline Sync lists recordings, not the 75 s / 3 min files capture writes. A customer's day of
/// recording read as dozens of identical rows, and ten "too old" files from one afternoon were ten
/// Delete buttons.

class _Sync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  _Sync(this.wals, {this.removeOnDelete = true, this.relistOnDiscover = const []});

  final List<Wal> wals;
  final bool removeOnDelete;
  final List<Wal> relistOnDiscover;
  final deleted = <Wal>[];
  final shared = <List<Wal>>[];
  int retried = 0;
  int discovered = 0;
  String? skipDeleteId;
  SyncJobCancelResult? serverCancel;
  final manuallyRetried = <Wal>[];

  @override
  Future<void> syncWal(Wal wal) async => manuallyRetried.add(wal);

  @override
  bool canPlayOrShareWal(Wal wal) => wal.filePath != null;
  @override
  Future<void> shareRecordingAsWav(List<Wal> wals) async => shared.add(wals);

  @override
  List<Wal> get retryableAttentionWals => wals.where((w) => isRetryableSyncState(w.syncDisplayState)).toList();
  @override
  Future<void> retryNeedsAttentionWals() async => retried++;

  @override
  SyncState get syncState => const SyncState();
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => wals;
  @override
  Future<SyncJobCancelResult?> deleteWal(Wal wal) async {
    deleted.add(wal);
    if (removeOnDelete && wal.id != skipDeleteId) {
      wals.remove(wal);
    }
    notifyListeners();
    return serverCancel;
  }

  @override
  int get clearableWalsCount => wals.length;
  @override
  List<Wal> get syncedWals => wals.where((w) => w.status == WalStatus.synced).toList();
  @override
  List<Wal> get pendingDeletableWals => wals.where((w) => w.status != WalStatus.synced).toList();
  @override
  Future<void> deleteAllPendingWals() async {
    for (final wal in List<Wal>.of(pendingDeletableWals)) {
      await deleteWal(wal);
    }
  }

  @override
  Future<void> deleteAllClearableWals() => deleteAllPendingWals();
  @override
  Future<void> deleteAllSyncedWals() async {
    for (final wal in List<Wal>.of(syncedWals)) {
      await deleteWal(wal);
    }
  }

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
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {
    discovered++;
    for (final wal in relistOnDiscover) {
      if (!wals.any((w) => w.id == wal.id && w.storage == wal.storage)) {
        wals.add(wal);
      }
    }
    notifyListeners();
  }

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

Future<_Sync> _pump(
  WidgetTester tester,
  List<Wal> wals, {
  bool removeOnDelete = true,
  List<Wal> relistOnDiscover = const [],
  bool render = false,
  double textScale = 1,
}) async {
  final sync = _Sync(wals, removeOnDelete: removeOnDelete, relistOnDiscover: relistOnDiscover);
  tester.view.physicalSize = render ? const Size(393, 852) : const Size(1170, 4000);
  tester.view.devicePixelRatio = render ? 1 : 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: Brightness.dark).copyWith(
          appBarTheme: const AppBarTheme(
              titleTextStyle: TextStyle(
                  fontFamily: 'SF Pro Display', fontSize: 20, fontWeight: FontWeight.w600, color: Colors.white)),
        ),
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
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
      )));
  await tester.pump();
  return sync;
}

void main() {
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });

  testWidgets('too-old recording downloads its whole audio without deleting or retrying it', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final sync = await _pump(tester, _tooOldAfternoon());
    await tester.tap(find.byKey(const Key('too_old_download')));
    await tester.pumpAndSettle();
    expect(sync.shared.single, hasLength(10), reason: 'one file for the whole recording, not one per chunk');
    expect(sync.deleted, isEmpty);
    expect(sync.manuallyRetried, isEmpty);
    expect(sync.wals, hasLength(10));
    debugDefaultTargetPlatformOverride = null;
  });

  for (final scale in [1.0, 1.5]) {
    testWidgets('render too-old recording at text scale $scale', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      await _pump(tester, _tooOldAfternoon(), render: true, textScale: scale);
      await tester.ensureVisible(find.byKey(const Key('too_old_download')));
      await tester.pumpAndSettle();
      expect(find.text('Download Audio'), findsOneWidget);
      // The copy names no day count: the server lookback is 60 days in production, 30 on dev.
      expect(
          find.text(
              "This recording is older than Omi's sync window, so Omi can't transcribe it. Download the audio to keep it, then delete it here."),
          findsOneWidget);
      for (final locale in AppLocalizations.supportedLocales) {
        expect(lookupAppLocalizations(locale).syncTooOldExplanation, isNot(matches(RegExp(r'\d'))), reason: '$locale');
      }
      await _frame(tester, scale == 1 ? '001-mobile-ios-too-old-recording' : '002-mobile-ios-too-old-larger-text');
      debugDefaultTargetPlatformOverride = null;
    });
  }

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

    await tester.tap(find.text('Synced'));
    await tester.pump();
    await tester.tap(find.textContaining('30m'));
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.textContaining('3m'), findsNWidgets(10));
  });

  testWidgets("a recording's files share as one recording", (tester) async {
    // A recording can be hundreds of 10 s files; sharing each one from its own page took a user hours.
    final synced = [
      for (final w in _tooOldAfternoon())
        w
          ..status = WalStatus.synced
          ..filePath = 'audio_${w.timerStart}.bin',
    ];
    final sync = await _pump(tester, synced);

    await tester.tap(find.text('Synced'));
    await tester.pump();
    await tester.tap(find.textContaining('30m'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Share Recording'));
    await tester.pump();

    expect(sync.shared, hasLength(1));
    expect(sync.shared.single, unorderedEquals(synced));
  });

  testWidgets('a recording with no audio on the phone offers no share', (tester) async {
    final synced = [for (final w in _tooOldAfternoon()) w..status = WalStatus.synced];
    await _pump(tester, synced);

    await tester.tap(find.text('Synced'));
    await tester.pump();
    await tester.tap(find.textContaining('30m'));
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('Share Recording'), findsNothing);
  });

  testWidgets('recordings that can never upload need attention without a dead Sync button', (tester) async {
    // #21177 follow-up: the card offered Sync for these, and Sync skipped them.
    await _pump(tester, _tooOldAfternoon());

    expect(find.textContaining('need attention'), findsWidgets);
    expect(find.text('Sync'), findsNothing);
    expect(find.byKey(const Key('offline_sync_card_retry_attention')), findsNothing);
  });

  testWidgets('a recording whose retry budget is spent offers Try Again, which retries it', (tester) async {
    final start = DateTime.now().subtract(const Duration(hours: 2)).millisecondsSinceEpoch ~/ 1000;
    final spent = Wal(
      timerStart: start,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'pendant',
    )..retryCount = walMaxAutoRetries;
    final sync = await _pump(tester, [spent]);

    final cardRetry = find.byKey(const Key('offline_sync_card_retry_attention'));
    expect(find.text('Sync'), findsNothing);
    expect(cardRetry, findsOneWidget);

    await tester.tap(cardRetry);
    await tester.pump();

    expect(sync.retried, 1);
  });

  testWidgets('a persisted HTTP refusal hides Retry and keeps Share Recording reachable', (tester) async {
    final wals = _tooOldAfternoon().take(2).toList();
    wals.first
      ..status = WalStatus.uploadRejected
      ..filePath = 'audio_refused.bin';
    final sync = await _pump(tester, wals);

    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(sync.manuallyRetried, isEmpty);

    await tester.tap(find.textContaining('6m').last);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Share Recording'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing, reason: 'automatic recovery owns deterministic refusals');
  });

  testWidgets('swiping a grouped recording row confirms once and deletes every file in the block', (tester) async {
    final sync = await _pump(tester, _tooOldAfternoon());

    await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    expect(sync.deleted, hasLength(10));
    expect(sync.wals, isEmpty);
  });

  List<Wal> uploadedHeld() {
    final start = DateTime.now().subtract(const Duration(hours: 3)).millisecondsSinceEpoch ~/ 1000;
    return [
      Wal(
        timerStart: start,
        codec: BleAudioCodec.opus,
        seconds: 600,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'pendant',
        filePath: 'held.bin',
      )..jobId = 'bp_synthetic',
    ];
  }

  for (final render in [false, true]) {
    testWidgets('swiping an uploaded, untranscribed recording says the server copy is erased too (render $render)',
        (tester) async {
      ServerCancelPause.instance.reset();
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      final sync = await _pump(tester, uploadedHeld(), render: render);
      sync.serverCancel = const SyncJobCancelResult(SyncJobCancelOutcome.cancelled);
      await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
      await tester.pumpAndSettle();
      expect(find.text('Delete Everywhere?'), findsOneWidget);
      expect(
          find.text("This recording is uploaded but not transcribed yet. Deleting it also permanently erases the copy "
              "on Omi's servers, so it will never be transcribed. This can't be undone."),
          findsOneWidget);
      if (render) await _frame(tester, '003-mobile-ios-delete-everywhere-confirm');
      await tester.tap(find.text('Delete').last);
      await tester.pumpAndSettle();
      expect(sync.deleted, hasLength(1));
      expect(find.text('Already transcribed. Delete its conversation to remove it.'), findsNothing);
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('deleting a recording the server already transcribed points to its conversation', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    final sync = await _pump(tester, uploadedHeld());
    sync.serverCancel = const SyncJobCancelResult(SyncJobCancelOutcome.alreadyProcessed, conversationIds: ['c1']);
    await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Already transcribed. Delete its conversation to remove it.'), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 5));
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('swiping a recording whose device delete fails snaps back instead of asserting', (tester) async {
    final start = DateTime.now().subtract(const Duration(minutes: 10)).millisecondsSinceEpoch ~/ 1000;
    final ringWal = Wal(
      timerStart: start,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.flashPage,
      device: 'omi_ring',
    );
    final sync = await _pump(tester, [ringWal], removeOnDelete: false);

    await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    expect(sync.deleted, [ringWal]);
    expect(sync.wals, [ringWal]);
    expect(find.byKey(ValueKey('${sync.wals.first.id}#${sync.wals.first.storage.name}')), findsOneWidget);
    expect(find.text('Failed to delete some items'), findsOneWidget);
  });

  testWidgets('swiping an SD-card recording verifies the device listing when StorageSync drops the local row', (
    tester,
  ) async {
    final start = DateTime.now().subtract(const Duration(minutes: 10)).millisecondsSinceEpoch ~/ 1000;
    final sdcardWal = Wal(
      timerStart: start,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'omi_devkit',
    );
    final sync = await _pump(tester, [sdcardWal], removeOnDelete: true, relistOnDiscover: [sdcardWal]);

    await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    expect(sync.deleted, [sdcardWal]);
    expect(sync.discovered, greaterThanOrEqualTo(2));
    expect(sync.wals, [sdcardWal]);
    expect(find.byKey(ValueKey('${sync.wals.first.id}#${sync.wals.first.storage.name}')), findsOneWidget);
    expect(find.text('Failed to delete some items'), findsOneWidget);
  });
  group('delete confirmation tells the truth about uploaded audio while server cancel is paused', () {
    // The server's owner-cancel switch was last seen off: the server keeps processing for now.
    setUp(() => ServerCancelPause.instance.reset(pausedUntil: 4102444800));
    tearDown(() => ServerCancelPause.instance.reset());
    final en = lookupAppLocalizations(const Locale('en'));
    const uploadedCopy =
        "This recording is already uploaded and Omi is processing it. Deleting it here removes the phone's copy. If processing fails, Omi can't retry from this phone.";

    Wal phoneWal(int ageMinutes, WalStatus status) => Wal(
          timerStart: DateTime.now().subtract(Duration(minutes: ageMinutes)).millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: status,
          storage: WalStorage.disk,
          device: 'pendant',
        )..jobId = status == WalStatus.uploaded ? 'bp_synthetic' : null;

    Future<void> swipe(WidgetTester tester) async {
      await tester.drag(find.byType(Dismissible).first, const Offset(-600, 0));
      await tester.pumpAndSettle();
    }

    test('the uploaded copy is the phone-only message', () {
      expect(en.deleteWhileProcessingMessage, uploadedCopy);
    });

    testWidgets('an uploaded recording says deleting removes the phone copy and a failure cannot be retried',
        (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      final sync = await _pump(tester, [phoneWal(10, WalStatus.uploaded)], render: true);
      await swipe(tester);
      expect(find.text(en.deleteWhileProcessingTitle), findsOneWidget);
      expect(find.text(uploadedCopy), findsOneWidget);
      expect(find.text(en.thisCannotBeUndone), findsNothing);
      await _frame(tester, '004-mobile-ios-delete-uploaded-cancel-paused');
      await tester.tap(find.text('Delete').last);
      await tester.pumpAndSettle();
      expect(sync.deleted, hasLength(1), reason: 'copy only: the delete itself is unchanged');
      debugDefaultTargetPlatformOverride = null;
    });

    testWidgets('a recording not yet uploaded keeps the cannot-be-undone warning', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      await _pump(tester, [phoneWal(10, WalStatus.miss)], render: true);
      await swipe(tester);
      expect(find.text(en.deleteRecording), findsOneWidget);
      expect(find.text(en.thisCannotBeUndone), findsOneWidget);
      expect(find.text(uploadedCopy), findsNothing);
      await _frame(tester, '002-mobile-ios-delete-not-uploaded-warning');
      debugDefaultTargetPlatformOverride = null;
    });

    testWidgets('a recording with any file not yet uploaded keeps the warning', (tester) async {
      // Two files one minute apart form one recording; one is uploaded, one is still only on the phone.
      await _pump(tester, [phoneWal(10, WalStatus.uploaded), phoneWal(11, WalStatus.miss)]);
      expect(find.byType(Dismissible), findsOneWidget);
      await swipe(tester);
      expect(find.text(en.thisCannotBeUndone), findsOneWidget);
      expect(find.text(uploadedCopy), findsNothing);
    });

    testWidgets('a recording of uploaded and already processed files shows the phone-only message', (tester) async {
      await _pump(tester, [phoneWal(10, WalStatus.uploaded), phoneWal(11, WalStatus.synced)]);
      expect(find.byType(Dismissible), findsOneWidget);
      await swipe(tester);
      expect(find.text(uploadedCopy), findsOneWidget);
    });
  });

  testWidgets('partial bulk Pending cleanup reports failure and keeps the skipped recording', (tester) async {
    final rows = _tooOldAfternoon();
    final kept = rows.first;
    final sync = await _pump(tester, rows);
    sync.skipDeleteId = kept.id;
    await tester.tap(find.text('Manage Storage'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Clear').last);
    await tester.pumpAndSettle();
    expect(sync.wals, [kept]);
    expect(find.text('Failed to delete some items'), findsOneWidget);
    expect(find.text('Deleted pending recordings'), findsNothing);
  });
}
