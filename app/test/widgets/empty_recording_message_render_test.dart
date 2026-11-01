import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

/// Home empty state after a recording that did not become a conversation.
/// `--dart-define=OMI_EMPTY_RECORDING_UI_EVIDENCE_DIR=<dir>` writes 393×852 @3x PNGs.
void main() {
  const cases = <(String, String)>[
    ('empty-result', 'Not enough speech to make a conversation. Try talking for 30 seconds or more.'),
    ('discarded-only', 'That recording was too short or empty to keep.'),
  ];

  for (final platform in const [TargetPlatform.iOS, TargetPlatform.android]) {
    for (final item in cases) {
      testWidgets('${item.$1} renders on ${platform.name}', (tester) async {
        debugDefaultTargetPlatformOverride = platform;
        addTearDown(() => debugDefaultTargetPlatformOverride = null);
        tester.view.physicalSize = const Size(393 * 3, 852 * 3);
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final previousPalette = OmiColors.active;
        OmiColors.active = OmiPalette.light;
        addTearDown(() => OmiColors.active = previousPalette);
        final theme = buildOmiTheme(brightness: Brightness.light).copyWith(platform: platform);

        const evidence = String.fromEnvironment('OMI_EMPTY_RECORDING_UI_EVIDENCE_DIR');
        if (evidence.isNotEmpty) {
          await tester.runAsync(_loadEvidenceFonts);
        }

        const boundaryKey = ValueKey('empty-recording-evidence');
        await tester.pumpWidget(
          RepaintBoundary(
            key: boundaryKey,
            child: MaterialApp(
              locale: const Locale('en'),
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              theme: theme,
              debugShowCheckedModeBanner: false,
              home: Scaffold(
                backgroundColor: OmiPalette.light.surface0,
                body: Center(child: NoConversationsHero(message: item.$2)),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.text('No conversations yet'), findsOneWidget);
        expect(find.text(item.$2), findsOneWidget);

        if (evidence.isNotEmpty) {
          await tester.runAsync(() async {
            final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
            final image = await boundary.toImage(pixelRatio: 3);
            final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
            final dir = await Directory(evidence).create(recursive: true);
            final platformSlug = platform == TargetPlatform.iOS ? 'mobile-ios' : 'mobile-android';
            final ordinal = switch ((platform, item.$1)) {
              (TargetPlatform.iOS, 'empty-result') => '001',
              (TargetPlatform.android, 'empty-result') => '002',
              (TargetPlatform.iOS, 'discarded-only') => '003',
              (TargetPlatform.android, 'discarded-only') => '004',
              _ => '009',
            };
            final slug = item.$1 == 'empty-result' ? 'empty-recording' : 'discarded-only';
            await File('${dir.path}/$ordinal-$platformSlug-$slug.png').writeAsBytes(bytes!.buffer.asUint8List());
            image.dispose();
          });
        }
        debugDefaultTargetPlatformOverride = null;
      });
    }
  }
}

Future<void> _loadEvidenceFonts() async {
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
    'FlutterTest',
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  final icons = _materialIconsFont();
  final bytes = await icons.readAsBytes();
  final iconLoader = FontLoader('MaterialIcons')
    ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))));
  await iconLoader.load();
}

File _materialIconsFont() {
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10; i++) {
    final candidate = File('${dir.path}/artifacts/material_fonts/MaterialIcons-Regular.otf');
    if (candidate.existsSync()) return candidate;
    final direct = File('${dir.path}/material_fonts/MaterialIcons-Regular.otf');
    if (direct.existsSync()) return direct;
    if (dir.path == dir.parent.path) break;
    dir = dir.parent;
  }
  throw StateError('MaterialIcons-Regular.otf not found above ${Platform.resolvedExecutable}');
}
