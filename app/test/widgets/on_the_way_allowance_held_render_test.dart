import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_sync_views.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// On the Way with uploads parked behind the monthly allowance (SCA-5264), dark palette, iPhone
/// size. `--dart-define=OMI_ALLOWANCE_HELD_EVIDENCE_DIR=<dir>` writes a 393x852 @3x PNG.
const _evidence = String.fromEnvironment('OMI_ALLOWANCE_HELD_EVIDENCE_DIR');
final _boundary = GlobalKey();
final _now = DateTime(2026, 11, 28, 9);

class _FakeSync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
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

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  @override
  bool get isConnected => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _held(DateTime start, int seconds) => Wal(
      timerStart: start.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: WalStatus.uploaded,
      uploadedAt: _now.millisecondsSinceEpoch ~/ 1000,
      storage: WalStorage.disk,
      device: 'omi',
      allowanceHeldUntil: DateTime(2026, 12, 1).millisecondsSinceEpoch ~/ 1000,
    );

Future<void> _loadFonts() async {
  final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
  for (final entry in fonts) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List<dynamic>) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in const [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'FlutterTest',
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

void main() {
  setUpAll(_loadFonts);

  testWidgets('allowance-held uploads: when and how, with the upgrade row', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);

    final sync = _FakeSync([
      _held(DateTime(2026, 11, 19, 15, 10), 3 * 3600),
      _held(DateTime(2026, 11, 18, 9, 30), 5 * 3600),
    ]);
    await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MultiProvider(
        providers: [
          ChangeNotifierProvider<SyncProvider>.value(value: sync),
          ChangeNotifierProvider<ConnectivityProvider>.value(value: _Connectivity()),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          locale: const Locale('en'),
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: OnTheWayPage(multiFileSync: true, clock: () => _now),
        ),
      ),
    ));
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Will process on Dec 1 when your minutes renew'), findsOneWidget);
    expect(find.text('Processes Dec 1'), findsNWidgets(2));
    if (_evidence.isNotEmpty) {
      await tester.runAsync(() async {
        final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(_evidence).create(recursive: true);
        await File('$_evidence/001-mobile-ios-on-the-way-allowance-held.png')
            .writeAsBytes(Uint8List.sublistView(bytes!));
      });
    }
    debugDefaultTargetPlatformOverride = null;
  });
}
