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
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_views.dart';
import 'package:omi/ui/ui.dart';

import '../../helpers/sfpro_font_fixtures.dart';

// Device Settings stays calm: routine BLE drops are not listed on the page (the WAL keeps
// recording through them; the raw history lives in Diagnostics and its Send to support bundle),
// and an upload the server has not accepted yet reads as waiting, not as transcription being
// unavailable. The layout assertions run
// everywhere; with --dart-define=DEVICE_SETTINGS_RENDER_OUTPUT=<dir> the PNG used as PR evidence is
// written there too. All data is synthetic.

const _output = String.fromEnvironment('DEVICE_SETTINGS_RENDER_OUTPUT');
const _frame = Key('device_settings_frame');

class _Device extends ChangeNotifier implements DeviceProvider {
  final device = BtDevice(id: 'omi-evidence', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => device;
  @override
  BtDevice? get pairedDevice => null; // No BLE feature discovery in a hermetic test.
  @override
  bool get isConnected => true;
  @override
  bool get isSyncStalled => false;
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
  Future<void> getDeviceInfo({bool forceRefresh = false}) async {}

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

class _Sync extends ChangeNotifier implements SyncProvider {
  _Sync(this.wals);

  final List<Wal> wals;

  late final _views = WalDerivedViews(wals);
  @override
  WalDerivedViews get derivedWals {
    _views.refresh();
    return _views;
  }

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
  List<Wal> get displaySortedWals => [...wals]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// An upload the server took but never turned into a conversation: past its pending window, so
/// Device Settings shows the stalled-upload row. The audio stays on the phone.
Wal _stalledUpload() => Wal(
      timerStart: DateTime.now().subtract(const Duration(days: 40)).millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 3600,
      status: WalStatus.uploaded,
      uploadedAt: 0,
      storage: WalStorage.disk,
      device: 'pendant',
    );

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

  Future<void> writeFrame(WidgetTester tester, String name) async {
    expect(tester.takeException(), isNull);
    debugDefaultTargetPlatformOverride = null;
    if (_output.isEmpty) return;
    await tester.runAsync(() async {
      final render = tester.renderObject<RenderRepaintBoundary>(find.byKey(_frame));
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(_output).create(recursive: true);
      await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  Future<void> pumpDevice(WidgetTester tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final theme = buildOmiTheme(brightness: Brightness.light);

    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    final device = _Device();
    final capture = _Capture();
    final sync = _Sync([_stalledUpload()]);
    final conversations = ConversationProvider(isSignedIn: () => false);
    final home = HomeProvider();
    for (final d in [
      store.dispose,
      device.dispose,
      capture.dispose,
      sync.dispose,
      conversations.dispose,
      home.dispose
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
      child: RepaintBoundary(
        key: _frame,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          // AppBar supplies a non-inheriting style; pin the loaded fixture font.
          theme: theme.copyWith(
              appBarTheme: theme.appBarTheme.copyWith(
            titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'Roboto'),
          )),
          home: DeviceSettings(pendingWork: store),
        ),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 120));
  }

  testWidgets('Device Settings lists no disconnects and calls a stalled upload waiting', (tester) async {
    await pumpDevice(tester);
    final en = lookupAppLocalizations(const Locale('en'));
    expect(find.text('Recently'), findsNothing, reason: 'routine BLE drops are not a device-page section');
    expect(find.textContaining('Disconnected for'), findsNothing);
    final row = find.byKey(const Key('device_stalled_upload_details'));
    expect(row, findsOneWidget);
    expect(find.descendant(of: row, matching: find.text(en.deviceUploadsWaitingOnServer)), findsOneWidget);
    expect(find.descendant(of: row, matching: find.text(en.deviceUploadsWaitingOnServerSubtitle)), findsOneWidget);
    expect(find.text(en.transcriptionUnavailable), findsNothing);
    await writeFrame(tester, '002-mobile-ios-device-settings-after');
  });
}
