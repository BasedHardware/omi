import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/storefront_wire.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/on_device/on_device_at_cap_sheet.dart';
import 'package:omi/ui/ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Renders the at-cap allowance sheet for David's approval. Hermetic: no network, no device.
///
/// `flutter test test/widgets/on_device_at_cap_render_test.dart \
///   --dart-define=OMI_AT_CAP_EVIDENCE_DIR=<dir>`
const evidenceDir = String.fromEnvironment('OMI_AT_CAP_EVIDENCE_DIR');
const boundaryKey = Key('at_cap_evidence');

Future<void> _loadFonts(WidgetTester tester) async {
  await tester.runAsync(() async {
    final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
    for (final entry in fonts) {
      final loader = FontLoader(entry['family'] as String);
      for (final font in entry['fonts'] as List<dynamic>) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
    for (final family in [
      'Roboto',
      'CupertinoSystemText',
      'CupertinoSystemDisplay',
      '.SF UI Text',
      '.SF UI Display',
      'SF Pro Display',
      'FlutterTest',
      'Ahem'
    ]) {
      final loader = FontLoader(family)
        ..addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'))
        ..addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'));
      await loader.load();
    }
  });
}

Widget _conversationsBackground() {
  Widget row(String title, String meta) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: Icon(Icons.graphic_eq, color: OmiColors.textTertiary, size: 20),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: OmiType.body, maxLines: 1, overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Text(meta, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                ],
              ),
            ),
          ],
        ),
      );
  return Scaffold(
    body: SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
            child: Text('Conversations', textAlign: TextAlign.center, style: OmiType.title3),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
            child: Text('Today', style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ),
          row('Standup with the design team', '9:00 AM · 24m'),
          row('Walk with Sam', '8:10 AM · 12m'),
        ],
      ),
    ),
  );
}

Future<void> _pumpSheet(
  WidgetTester tester, {
  required bool dark,
  GeneratedStorefrontCapChoice? copy,
  DateTime? returnOn,
  bool selectUpgrade = false,
}) async {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final previousPalette = OmiColors.active;
  addTearDown(() => OmiColors.active = previousPalette);
  OmiColors.active = dark ? OmiPalette.dark : OmiPalette.light;
  await _loadFonts(tester);

  await tester.pumpWidget(
    RepaintBoundary(
      key: boundaryKey,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildOmiTheme(brightness: dark ? Brightness.dark : Brightness.light).copyWith(
          platform: TargetPlatform.iOS,
          textTheme: buildOmiTheme(brightness: dark ? Brightness.dark : Brightness.light)
              .textTheme
              .apply(fontFamily: 'SF Pro Display'),
        ),
        home: Builder(
          builder: (context) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              showOnDeviceAtCapSheet(context, liveHoursReturnOn: returnOn, copy: copy);
            });
            return _conversationsBackground();
          },
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  if (selectUpgrade) {
    await tester.tap(find.byKey(const Key('on_device_at_cap_upgrade')));
    await tester.pumpAndSettle();
  }
}

Future<void> _capture(WidgetTester tester, String name) async {
  if (evidenceDir.isEmpty) return;
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(evidenceDir).create(recursive: true);
    await File('$evidenceDir/$name').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('default allowance copy, dark', (tester) async {
    await _pumpSheet(tester, dark: true, returnOn: DateTime(2026, 12, 1));
    expect(find.text('You\'ve reached this month\'s limit'), findsOneWidget);
    await _capture(tester, '001-mobile-ios-at-cap-default-dark.png');
  });

  testWidgets('default allowance copy, light', (tester) async {
    await _pumpSheet(tester, dark: false, returnOn: DateTime(2026, 12, 1));
    await _capture(tester, '002-mobile-ios-at-cap-default-light.png');
  });

  testWidgets('upgrade selected, dark', (tester) async {
    await _pumpSheet(tester, dark: true, returnOn: DateTime(2026, 12, 1), selectUpgrade: true);
    await _capture(tester, '003-mobile-ios-at-cap-upgrade-selected-dark.png');
  });

  testWidgets('storefront ladder copy, dark', (tester) async {
    final copy = GeneratedStorefrontCapChoice.fromJson(
        jsonDecode(File('../backend/tests/fixtures/ladder_v1_at_cap.json').readAsStringSync()));
    await _pumpSheet(tester, dark: true, copy: copy, returnOn: DateTime(2026, 12, 1));
    expect(find.text(copy.title), findsOneWidget);
    await _capture(tester, '004-mobile-ios-at-cap-storefront-dark.png');
  });
}
