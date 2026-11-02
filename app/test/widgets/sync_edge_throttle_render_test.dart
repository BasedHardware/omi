import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

class _ThrottledSync extends ChangeNotifier implements SyncProvider {
  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isRateLimited => true;
  @override
  RateLimitReason get rateLimitReason => RateLimitReason.edgeThrottle;
  @override
  List<Wal> get allWals => [];
  @override
  List<Wal> get uploadedWals => [];
  @override
  List<Wal> get displaySortedWals => [];
  @override
  int get needsAttentionWalsCount => 0;
  @override
  int get clearableWalsCount => 0;
  @override
  bool get syncCompleted => false;
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _User extends ChangeNotifier implements UserProvider {
  @override
  bool get privateCloudSyncEnabled => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets('Offline Sync renders a neutral edge pause without a global busy banner', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final sync = _ThrottledSync(), device = _Device(), user = _User();
    addTearDown(sync.dispose);
    addTearDown(device.dispose);
    addTearDown(user.dispose);
    final previousPalette = OmiColors.active;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = previousPalette);
    final baseTheme = buildOmiTheme();
    final theme = baseTheme.copyWith(
      platform: TargetPlatform.iOS,
      textTheme: baseTheme.textTheme.apply(fontFamily: 'SF Pro Display'),
      primaryTextTheme: baseTheme.primaryTextTheme.apply(fontFamily: 'SF Pro Display'),
      appBarTheme: baseTheme.appBarTheme
          .copyWith(titleTextStyle: baseTheme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display')),
    );
    const boundaryKey = ValueKey('sync-evidence');
    const evidence = String.fromEnvironment('OMI_SYNC_UI_EVIDENCE_DIR');
    if (evidence.isNotEmpty) {
      // Load the actual bundled product fonts, not the widget-test box font.
      await tester.runAsync(() async {
        final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
        for (final entry in fonts) {
          final loader = FontLoader(entry['family'] as String);
          for (final font in entry['fonts'] as List<dynamic>) {
            loader.addFont(rootBundle.load(font['asset'] as String));
          }
          await loader.load();
        }

        for (final family in ['SF Pro Display']) {
          final loader = FontLoader(family);
          loader.addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'));
          loader.addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'));
          await loader.load();
        }
      });
    }
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<UserProvider>.value(value: user),
      ],
      child: RepaintBoundary(
          key: boundaryKey,
          child: MaterialApp(
            locale: const Locale('en'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            theme: theme,
            debugShowCheckedModeBanner: false,
            home: const AutoSyncPage(),
          )),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Syncing paused briefly — it will resume automatically'), findsOneWidget);
    expect(find.textContaining('Omi servers are busy'), findsNothing);
    expect(tester.takeException(), isNull);
    if (evidence.isNotEmpty) {
      await tester.runAsync(() async {
        final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
        final image = await boundary.toImage(pixelRatio: 2);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        final dir = await Directory(evidence).create(recursive: true);
        await File('${dir.path}/001-mobile-ios-sync-edge-paused.png').writeAsBytes(bytes!.buffer.asUint8List());
        image.dispose();
      });
    }
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
