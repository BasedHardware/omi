import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

// Pendant case: the wear session began at 03:07Z, a closed episode ended at 06:27Z, and it is 07:30Z.
// Before the fix the Listening row counted from the wear session start (4h 23m); after it counts from
// the closed episode's end (1h 3m). Only synthetic data is used.
final _now = DateTime.utc(2026, 11, 9, 7, 30);
final _wearStart = DateTime.utc(2026, 11, 9, 3, 7);
final _closedEnd = DateTime.utc(2026, 11, 9, 6, 27);

const _output = String.fromEnvironment('LIVE_ANCHOR_RENDER_OUTPUT');

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
    'Roboto',
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

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

class _Syncs {
  final phone = _PhoneSync();
}

class _WalService implements IWalService {
  @override
  dynamic getSyncs() => _Syncs();

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// A pendant capture that is streaming, with the wear session start given by the test.
class _PendantCapture extends CaptureProvider {
  _PendantCapture()
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

  DateTime? _startedAt;

  @override
  String? get liveCaptureSource => 'omi';

  @override
  String? get topConversationId => 'c1';

  @override
  DateTime? get liveCaptureStartedAt => _startedAt;

  set startedAt(DateTime? value) {
    _startedAt = value;
    notifyListeners();
  }
}

/// The episodes before this fix: no closed-episode floor, so the stored start stays at the wear start.
class _BeforeFixEpisodes extends EpisodeProvider {
  _BeforeFixEpisodes()
      : super(
          fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
          lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
          wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
          dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
          clock: () => _now,
        );

  @override
  DateTime? closedEpisodeFloor(DateTime now) => null;
}

/// The episodes after this fix: the closed Home episode that ended at 06:27Z supplies the floor.
EpisodeProvider _afterFixEpisodes() {
  final provider = EpisodeProvider(
    fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
    lookup: (_) async => const ApiSuccess(EpisodeRead.disabled),
    wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    dismiss: (id, itemId) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    clock: () => _now,
  );
  final earlier = Episode(
    id: 'earlier',
    live: false,
    startedAt: DateTime.utc(2026, 11, 9, 2, 26),
    lastActivityAt: _closedEnd,
    closedAt: _closedEnd,
    closeReason: 'hard_cap',
    title: 'Earlier conversation',
    conversationIds: const ['c0'],
  );
  provider.debugSetLive(null, enabled: true);
  provider.debugSetHomeEpisodes([earlier]);
  return provider;
}

Future<void> _pumpFrame(
  WidgetTester tester,
  Widget child, {
  required CaptureProvider capture,
  required EpisodeProvider episodes,
  required GlobalKey boundary,
}) async {
  tester.view.physicalSize = const Size(393, 852);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final device = _StubDeviceProvider();
  final usage = UsageProvider();
  addTearDown(device.dispose);
  addTearDown(usage.dispose);
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
        ChangeNotifierProvider(
          create: (_) => PeopleProvider(loadPeople: () async => const PeopleListResponse(people: [])),
        ),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => _StubConnectivityProvider()),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: RepaintBoundary(
        key: boundary,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.dark),
          locale: const Locale('en'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: child,
        ),
      ),
    ),
  );
  for (var i = 0; i < 3; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> _writeFrame(WidgetTester tester, GlobalKey boundary, String name) async {
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
  });
}

void main() {
  setUpAll(_loadFonts);

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  void frames(String label, EpisodeProvider Function() episodesFor, {required String tag}) {
    testWidgets('pendant listening row and live page, $label', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      final capture = _PendantCapture();
      addTearDown(capture.dispose);
      capture.startedAt = _wearStart;
      final episodes = episodesFor();
      addTearDown(episodes.dispose);

      final rowBoundary = GlobalKey();
      await _pumpFrame(
        tester,
        const Scaffold(body: SafeArea(child: LiveEpisodeRow())),
        capture: capture,
        episodes: episodes,
        boundary: rowBoundary,
      );
      expect(tester.takeException(), isNull);
      await _writeFrame(tester, rowBoundary, '001-mobile-ios-listening-row-$tag');

      final pageBoundary = GlobalKey();
      await _pumpFrame(
        tester,
        const LiveEpisodePage(),
        capture: capture,
        episodes: episodes,
        boundary: pageBoundary,
      );
      expect(tester.takeException(), isNull);
      await _writeFrame(tester, pageBoundary, '002-mobile-ios-live-page-$tag');
      // Reset in the body: the binding asserts the override is unset before tear-down runs.
      debugDefaultTargetPlatformOverride = null;
    });
  }

  frames('before the fix', _BeforeFixEpisodes.new, tag: 'before-fix');
  frames('after the fix', _afterFixEpisodes, tag: 'after-fix');
}
