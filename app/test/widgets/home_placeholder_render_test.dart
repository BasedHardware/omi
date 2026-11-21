import 'package:omi/env/env.dart';
import '../helpers/home_fixture_env.dart';
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
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

const _output = String.fromEnvironment('HOME_SETTLE_RENDER_OUTPUT');

Future<void> _fonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final entry in manifest) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List) {
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
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
}

ThemeData _evidenceTheme() {
  final theme = buildOmiTheme(brightness: Brightness.dark);
  return theme.copyWith(
      appBarTheme: theme.appBarTheme.copyWith(
    titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
  ));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(HomeFixtureEnv());
    await _fonts();
  });
  for (final before in [true, false]) {
    testWidgets('Home placeholder ${before ? 'before' : 'after'}', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      tester.view.physicalSize = const Size(393, 400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final previous = OmiColors.active;
      OmiColors.active = OmiPalette.dark;
      addTearDown(() => OmiColors.active = previous);
      final start = DateTime(2026, 11, 3, 9);
      final a = ServerConversation(
          id: 'fixture-a',
          createdAt: start,
          startedAt: start,
          finishedAt: start.add(const Duration(minutes: 5)),
          structured: Structured('Um, so the idea is…', ''));
      final b = ServerConversation(
          id: 'fixture-b', createdAt: start, startedAt: start, structured: Structured('Thank you.', ''));
      final e = Episode(
          id: 'fixture-e',
          live: false,
          startedAt: start,
          lastActivityAt: start.add(const Duration(minutes: 20)),
          closedAt: start.add(const Duration(minutes: 20)),
          conversationIds: [a.id, b.id],
          members: [a, b]);
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(
          key: boundary,
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            theme: _evidenceTheme(),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Builder(builder: (context) {
              final row = buildHomeRows([a, b], [e],
                      enabled: true,
                      finishingTitle: AppLocalizations.of(context).episodeFinishingUp,
                      now: start.add(const Duration(minutes: 21)))
                  .single;
              // The before fixture reproduces the base adapter's primary.structured
              // using the same production row widget. No customer data is used.
              final shown = before
                  ? ServerConversation(
                      id: row.conversation.id,
                      createdAt: start,
                      startedAt: start,
                      finishedAt: e.lastActivityAt,
                      structured: a.structured)
                  : row.conversation;
              return Scaffold(
                  appBar: AppBar(title: const Text('Home')),
                  body: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [const SizedBox(height: 24), ProcessingConversationRow(conversation: shown, episode: e)],
                  ));
            }),
          )));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.text('Processing…'), findsOneWidget, reason: 'Processing rows never echo a member title');
      if (_output.isNotEmpty) {
        await tester.runAsync(() async {
          final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await render.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory(_output).create(recursive: true);
          final name = before ? '001-mobile-ios-placeholder-before' : '002-mobile-ios-placeholder-after';
          await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
