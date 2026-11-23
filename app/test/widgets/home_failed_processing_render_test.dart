// Renders the production Home feed with an age-failed row and verifies terminal reachability.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../helpers/home_fixture_env.dart';
import '../helpers/sfpro_font_fixtures.dart';
import '../support/typed_conversation_screen.dart';

const _output = String.fromEnvironment('HOME_FAILED_RENDER_OUTPUT');

void main() {
  setUpAll(() => Env.init(HomeFixtureEnv()));
  testWidgets('Home keeps an age-failed row openable with Retry and no processing or polling', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    final previousPalette = OmiColors.active;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = previousPalette);
    if (_output.isNotEmpty) await tester.runAsync(_loadEvidenceFonts);
    final started = DateTime(2026, 11, 8, 9);
    final failed = ServerConversation(
        id: 'expired-planning',
        createdAt: started,
        startedAt: started,
        finishedAt: started.add(const Duration(minutes: 18)),
        status: ConversationStatus.processing,
        homeStep: 'failed',
        structured: Structured('Processing', '', emoji: '📝'));
    var probes = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: [failed], ok: true),
      conversationLifecycleFetcher: (_) async {
        probes++;
        return (item: failed, ok: true);
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider,
        theme: buildOmiTheme(brightness: Brightness.dark).copyWith(platform: TargetPlatform.iOS));
    await provider.fetchConversations();
    final boundary = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(key: boundary, child: screen));
    await tester.pumpAndSettle();
    expect(find.byType(ConversationListItem), findsOneWidget);
    expect(find.text("Omi couldn't finish"), findsOneWidget);
    expect(find.byKey(const Key('conversation_summary_retry_button')), findsOneWidget);
    expect(find.byType(ProcessingConversationRow), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    final tile = find.descendant(of: find.byType(ConversationListItem), matching: find.byType(InkWell));
    expect(tester.widget<InkWell>(tile.first).onTap, isNotNull);
    await tester.pump(const Duration(minutes: 2));
    expect(probes, 0);
    expect(tester.takeException(), isNull);
    if (_output.isNotEmpty) {
      await tester.runAsync(() async {
        final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(_output).create(recursive: true);
        await File('$_output/002-mobile-ios-home-failed-processing.png').writeAsBytes(bytes!.buffer.asUint8List());
      });
    }
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    debugDefaultTargetPlatformOverride = null;
  });
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
