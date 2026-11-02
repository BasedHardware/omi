import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal_derived_views.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';

import '../../helpers/sfpro_font_fixtures.dart';

// Renders the sync-attention surfaces David chose on 10-27: the Catching up stat tile (option C),
// On the Way by day (option B) and its support details. The layout assertions run everywhere;
// with --dart-define=SYNC_ATTENTION_EVIDENCE_OUTPUT=<dir> the PNGs used as PR evidence are
// written there too.

class _Device extends ChangeNotifier implements DeviceProvider {
  final device = BtDevice(id: 'omi-evidence', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => device;
  @override
  BtDevice? get pairedDevice => null; // No BLE feature discovery in a hermetic test.
  @override
  bool get isConnected => true;
  @override
  bool get isSyncStalled => false; // The watchdog's stall (#15501) is not under test here.
  @override
  bool get isConnecting => false;
  @override
  int get batteryLevel => 72;
  @override
  bool get isCharging => false;
  @override
  bool get havingNewFirmware => false;
  @override
  String get latestStableFirmwareVersion => '';
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
  BtDevice? get recordingDevice => null;
  @override
  double get bleReceiveRateKbps => 0;
  @override
  double get wsSendRateKbps => 0;
  @override
  String? get liveCaptureSource => null;
  @override
  bool get isPaused => false;
  @override
  bool get havingRecordingDevice => false;
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

class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync(this.wals);

  final List<Wal> wals;

  late final _views = WalDerivedViews(wals);
  @override
  WalDerivedViews get derivedWals {
    _views.refresh();
    return _views;
  }

  @override
  List<Wal> get uploadedWals => derivedWals.uploaded;
  @override
  List<Wal> get pendingSyncWals => derivedWals.syncing;
  @override
  List<Wal> get attentionWals => derivedWals.attention;
  @override
  List<Wal> get refusedWals => derivedWals.refused;
  @override
  List<Wal> get pendingWorkWals => derivedWals.pendingWork;
  @override
  int get needsAttentionWalsCount => attentionWals.length;
  @override
  int get terminallyFailedWalsCount => refusedWals.length;
  @override
  WalRefusalSummary get refusalSummary => derivedWals.refusalSummary();
  @override
  void dispose() {
    _views.dispose();
    super.dispose();
  }

  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isSyncing => false;
  @override
  bool get isRateLimited => false;
  @override
  int get missingWalsInSeconds => 0;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => [...wals]..sort((a, b) => b.timerStart.compareTo(a.timerStart));

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _wal(DateTime start, int minutes, WalStatus status,
    {WalStorage storage = WalStorage.disk, String? rejectionReason}) {
  return Wal(
    timerStart: start.millisecondsSinceEpoch ~/ 1000,
    codec: BleAudioCodec.opus,
    seconds: minutes * 60,
    status: status,
    storage: storage,
    device: 'pendant',
    uploadRejectionReason: rejectionReason,
  );
}

// 9:10 AM local on a Sunday: every fixture is local time so the day split does not depend on the
// machine's time zone.
final _now = DateTime(2026, 10, 18, 9, 10);
DateTime _at(int daysAgo, int hour, int minute) => DateTime(2026, 10, 18 - daysAgo, hour, minute);

/// Mixed days: today uploading, yesterday on the server, two older days waiting, plus failures and
/// refusals that stay off the page and show only in support.
List<Wal> _mixedDays() => [
      _wal(_at(0, 8, 41), 14, WalStatus.miss)..isSyncing = true,
      _wal(_at(0, 7, 58), 23, WalStatus.miss),
      _wal(_at(1, 19, 5), 96, WalStatus.uploaded),
      _wal(_at(1, 12, 30), 41, WalStatus.uploaded),
      _wal(_at(2, 15, 0), 128, WalStatus.miss, storage: WalStorage.sdcard),
      _wal(_at(3, 10, 0), 166, WalStatus.miss, storage: WalStorage.sdcard),
      _wal(_at(3, 9, 0), 5, WalStatus.outsideRecoveryWindow),
      _wal(_at(2, 8, 30), 2, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(_at(1, 8, 0), 4, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.tooLarge),
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
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
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  const output = String.fromEnvironment('SYNC_ATTENTION_EVIDENCE_OUTPUT');
  const frame = Key('sync_attention_frame');

  Future<void> writeFrame(WidgetTester tester, String name) async {
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
    if (output.isEmpty) return;
    await tester.runAsync(() async {
      final render = tester.renderObject<RenderRepaintBoundary>(find.byKey(frame));
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  /// iPhone viewport with iOS widgets and metrics; [writeFrame] resets the platform at the end of
  /// each test body.
  void phone(WidgetTester tester) {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  Widget app(Widget home, {Brightness brightness = Brightness.light, double textScale = 1}) {
    OmiColors.active = OmiColors.forBrightness(brightness);
    final theme = buildOmiTheme(brightness: brightness);
    return RepaintBoundary(
      key: frame,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        // AppBar supplies a non-inheriting style; pin the loaded fixture font rather than letting
        // the test engine render its default block glyphs.
        theme: theme.copyWith(
            appBarTheme: theme.appBarTheme.copyWith(
          titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'Roboto'),
        )),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: home,
      ),
    );
  }

  Future<void> pumpDevice(WidgetTester tester, _FakeSync sync) async {
    phone(tester);
    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    final device = _Device();
    final capture = _Capture();
    final conversations = ConversationProvider(isSignedIn: () => false);
    final home = HomeProvider();
    for (final d in [
      store.dispose,
      device.dispose,
      capture.dispose,
      conversations.dispose,
      home.dispose,
      sync.dispose
    ]) {
      addTearDown(d);
    }
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
      ],
      child: app(DeviceSettings(pendingWork: store)),
    ));
    await tester.pump(const Duration(milliseconds: 120));
  }

  Future<void> pumpOnTheWay(WidgetTester tester,
      {Brightness brightness = Brightness.light, double textScale = 1}) async {
    phone(tester);
    final sync = _FakeSync(_mixedDays());
    addTearDown(sync.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<SyncProvider>.value(
      value: sync,
      child: app(
        OnTheWayPage(syncProvider: sync, multiFileSync: true, clock: () => _now),
        brightness: brightness,
        textScale: textScale,
      ),
    ));
    await tester.pump(const Duration(milliseconds: 120));
  }

  testWidgets('Device Settings with catch-up pending: the third tile is Catching up', (tester) async {
    await pumpDevice(
        tester,
        _FakeSync([
          _wal(_at(0, 7, 0), 300, WalStatus.miss, storage: WalStorage.sdcard),
          _wal(_at(0, 3, 0), 194, WalStatus.miss, storage: WalStorage.sdcard),
        ]));
    final tile = find.byKey(const Key('device_stat_catching_up'));
    expect(tile, findsOneWidget);
    expect(find.descendant(of: tile, matching: find.text('8h 14m')), findsOneWidget);
    expect(find.byKey(const Key('device_stat_on_device')), findsNothing);
    expect(find.text('Waiting to sync'), findsNothing, reason: 'no stage words');
    expect(find.byKey(const Key('device_catching_up_span')), findsNothing, reason: 'no date range');
    await writeFrame(tester, '001-mobile-ios-device-catching-up-pending');
  });

  testWidgets('Device Settings with nothing pending: the tile is On Device again', (tester) async {
    await pumpDevice(tester, _FakeSync([_wal(_at(0, 7, 0), 30, WalStatus.synced)]));
    expect(find.byKey(const Key('device_stat_catching_up')), findsNothing);
    expect(find.byKey(const Key('device_stat_on_device')), findsOneWidget);
    expect(find.text('Catching up'), findsNothing);
    await writeFrame(tester, '002-mobile-ios-device-nothing-pending');
  });

  testWidgets('On the Way with mixed days', (tester) async {
    await pumpOnTheWay(tester);
    expect(find.text('7h 48m catching up'), findsOneWidget);
    for (final status in ['Uploading', 'Transcribing…', 'Next', 'Queued']) {
      expect(find.text(status), findsOneWidget, reason: status);
    }
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    expect(find.text('Invalid recording date'), findsNothing);
    await writeFrame(tester, '003-mobile-ios-on-the-way-mixed-days');
  });

  testWidgets('On the Way details for support', (tester) async {
    await pumpOnTheWay(tester);
    await tester.tap(find.byKey(const Key('on_the_way_details_for_support')));
    await tester.pumpAndSettle();
    expect(find.text('Invalid recording date'), findsOneWidget);
    expect(find.text('uploadRejected · invalid_capture_time · 400'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    await writeFrame(tester, '004-mobile-ios-on-the-way-support-details');
  });

  testWidgets('On the Way in dark mode', (tester) async {
    await pumpOnTheWay(tester, brightness: Brightness.dark);
    expect(find.text('7h 48m catching up'), findsOneWidget);
    await writeFrame(tester, '005-mobile-ios-on-the-way-dark');
  });

  testWidgets('On the Way at the largest text size', (tester) async {
    // iOS's largest accessibility size (AX5) sets body text at about 3.1x.
    await pumpOnTheWay(tester, textScale: 3.1);
    expect(find.text('7h 48m catching up'), findsOneWidget);
    await writeFrame(tester, '006-mobile-ios-on-the-way-largest-text');
  });
}
