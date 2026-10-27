import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/ui/ui.dart';

import '../../helpers/sfpro_font_fixtures.dart';

// Renders the sync-attention surfaces this PR made honest: On the Way rows
// that name their length and the refusal reason with Retry/Delete actions, and
// the Device stats that count a running episode and name the phone queue. The
// layout assertions run everywhere; with
// --dart-define=SYNC_ATTENTION_EVIDENCE_OUTPUT=<dir> the PNGs used as PR
// evidence are written there too (the pattern of open_loop_evidence_test).

class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync(this.wals);

  final List<Wal> wals;

  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isSyncing => false;
  @override
  bool get isRateLimited => false;
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

// 9:10 AM local: every fixture is local time so the day split does not depend
// on the machine's time zone.
final _now = DateTime(2026, 10, 18, 9, 10);
DateTime _at(int hour, int minute) => DateTime(2026, 10, 18, hour, minute);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);

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

  const output = String.fromEnvironment('SYNC_ATTENTION_EVIDENCE_OUTPUT');

  Future<void> writeFrame(WidgetTester tester, Key frame, String name) async {
    if (output.isEmpty) return;
    await tester.runAsync(() async {
      final render = tester.renderObject<RenderRepaintBoundary>(find.byKey(frame));
      final image = await render.toImage(pixelRatio: 2);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  Widget app({required Widget home}) {
    return MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildOmiTheme(brightness: Brightness.dark),
      home: Scaffold(
        backgroundColor: OmiColors.surface0,
        body: home,
      ),
    );
  }

  testWidgets('On the Way rows show length, reason and actions', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 844 * 2);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    OnTheWayPage.resetFolds();
    final sync = _FakeSync([
      _wal(_at(8, 41), 14, WalStatus.uploaded),
      _wal(_at(7, 58), 3, WalStatus.miss)..isSyncing = true,
      _wal(_at(7, 40), 1, WalStatus.miss, storage: WalStorage.sdcard),
      _wal(_at(9, 0), 5, WalStatus.outsideRecoveryWindow),
      _wal(_at(8, 30), 2, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(_at(8, 0), 4, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.tooLarge),
      // A pendant clock that was never set: no plausible time, but the length
      // and the refusal still read.
      _wal(DateTime(1985, 9, 5, 16, 17), 3, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
    ]);
    await tester.pumpWidget(
      ChangeNotifierProvider<SyncProvider>.value(
        value: sync,
        child: app(
          home: RepaintBoundary(
            key: const Key('sync_attention_on_the_way'),
            child: OnTheWayPage(syncProvider: sync, multiFileSync: true, clock: () => _now),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 120));

    expect(find.text('Invalid recording date'), findsNWidgets(2));
    expect(find.text('Too large'), findsOneWidget);
    expect(find.text('Too old to sync — Omi can\'t accept it'), findsOneWidget);
    // The invalid-date rows keep Retry; the too-large row offers Delete only.
    expect(find.text('Try Again'), findsNWidgets(2));
    expect(find.text('3m'), findsOneWidget, reason: 'the undated row still shows its length');
    // The 7:58 uploading piece and the 8:00 refused piece are one recording;
    // the undated 1985 row lists outside the day totals.
    expect(find.text('5 recordings · 28m on the way'), findsOneWidget);
    expect(find.text('5 recordings · 28m · 1 uploading · 3 need attention'), findsOneWidget);

    await writeFrame(tester, const Key('sync_attention_on_the_way'), 'on-the-way-rows');
  });

  testWidgets('Device stats count the live episode and name the phone queue', (tester) async {
    tester.view.physicalSize = const Size(390 * 2, 400 * 2);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      app(
        // Shrink-wrapped so the captured frame is the tiles' real height, not
        // the viewport: the body's tight constraints would otherwise stretch
        // the boundary to full height with empty space under the tiles.
        home: const Align(
          alignment: Alignment.topCenter,
          child: RepaintBoundary(
            key: Key('sync_attention_device_stats'),
            child: Padding(
              padding: EdgeInsets.all(16),
              child: DeviceStatsRow(
                batteryLevel: 72,
                isCharging: true,
                heardTodaySeconds: 33 * 60,
                onDeviceSeconds: 0,
                phoneQueueSeconds: 7 * 3600 + 45 * 60,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 120));

    expect(find.text('33m'), findsOneWidget);
    expect(find.text('7h 45m on phone'), findsOneWidget);
    expect(find.text('0s'), findsOneWidget, reason: 'on-device audio reads 0s only when none is left');

    final statsHeight =
        tester.renderObject<RenderBox>(find.byKey(const Key('sync_attention_device_stats'))).size.height;
    expect(statsHeight, lessThan(200), reason: 'the captured frame is the tiles, not the viewport');

    // One row height: the On Device tile's two caption lines raise the whole
    // row, not just their own tile — no tile stands shorter beside a taller one.
    final heights = [
      for (final key in ['device_stat_battery', 'device_stat_heard_today', 'device_stat_on_device'])
        tester.renderObject<RenderBox>(find.byKey(Key(key))).size.height,
    ];
    expect(heights.toSet(), hasLength(1), reason: 'the three tiles share one height: $heights');
    expect(heights.first, greaterThanOrEqualTo(84), reason: 'the 84pt minimum still holds');

    await writeFrame(tester, const Key('sync_attention_device_stats'), 'device-stats');
  });
}
