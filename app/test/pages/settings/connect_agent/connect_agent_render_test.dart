import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/ask_agent_sheet.dart';
import 'package:omi/pages/settings/connect_agent/connect_agent_page.dart';
import 'package:omi/ui/ui.dart';

import 'connect_agent_fixture.dart';

/// Renders every Connect an Agent state on an iPhone-sized screen with the app's real fonts and
/// asserts each lays out without overflow. With
/// `--dart-define=CONNECT_AGENT_RENDER_OUTPUT=<dir>` it also writes the PNGs used as PR evidence.
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
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(rootBundle.load('assets/fonts/SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  // The prompt preview asks for `monospace`, then Menlo, which iOS provides. Use a local monospace
  // face for the evidence when the machine has one; the layout assertions do not depend on it.
  const courier = '/System/Library/Fonts/Supplemental/Courier New.ttf';
  if (File(courier).existsSync()) {
    for (final family in ['monospace', 'Menlo']) {
      final mono = FontLoader(family)..addFont(Future.value(ByteData.sublistView(File(courier).readAsBytesSync())));
      await mono.load();
    }
  }
}

/// On a phone, text with no family (the app bar title) uses the system font; the test engine's
/// default is a placeholder face, so the evidence theme names SF Pro for it.
ThemeData _evidenceTheme() {
  final theme = buildOmiTheme(brightness: Brightness.dark);
  return theme.copyWith(
    appBarTheme: theme.appBarTheme.copyWith(
      titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
  );
}

ServerConversation _conversation() => ServerConversation.fromJson({
      'id': 'conv-weekly-sync',
      'created_at': DateTime(2026, 10, 15, 10, 0).toUtc().toIso8601String(),
      'started_at': DateTime(2026, 10, 15, 10, 0).toUtc().toIso8601String(),
      'finished_at': DateTime(2026, 10, 15, 10, 42).toUtc().toIso8601String(),
      'structured': {'title': 'Weekly product sync', 'overview': '', 'emoji': '', 'category': 'work'},
      'status': 'completed',
      'transcript_segments': [],
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadFonts);
  const output = String.fromEnvironment('CONNECT_AGENT_RENDER_OUTPUT');
  final boundary = GlobalKey();

  Future<void> writeFrame(WidgetTester tester, String name) async {
    if (output.isEmpty) return;
    await tester.runAsync(() async {
      final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  /// Checks the frame, writes it when an output directory is set, and clears the platform
  /// override before the test ends (the binding asserts it is unset).
  Future<void> shoot(WidgetTester tester, String name) async {
    expect(tester.takeException(), isNull, reason: '$name rendered with an exception');
    await writeFrame(tester, name);
    debugDefaultTargetPlatformOverride = null;
  }

  Future<FakeAgentBackend> pump(WidgetTester tester, FakeAgentBackend backend, {Widget? home}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: _evidenceTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: home ?? ConnectAgentPage(service: backend.service()),
      ),
    ));
    await settle(tester);
    return backend;
  }

  testWidgets('1 hub', (tester) async {
    await pump(
      tester,
      FakeAgentBackend(chatGptConnected: true, keys: {'Muse': DateTime.now().subtract(const Duration(hours: 2))}),
    );
    await shoot(tester, '1-connect-an-agent');
  });

  testWidgets('2 ChatGPT one-tap sheet', (tester) async {
    await pump(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_chatgpt')));
    await settle(tester);
    await shoot(tester, '2-chatgpt-connect-sheet');
  });

  testWidgets('3 ChatGPT connected', (tester) async {
    await pump(tester, FakeAgentBackend(chatGptConnected: true));
    await tester.tap(find.byKey(const ValueKey('connect_agent_chatgpt')));
    await settle(tester);
    await shoot(tester, '3-chatgpt-connected');
  });

  testWidgets('3b partial ChatGPT grant: reconnect sheet offers Disconnect', (tester) async {
    await pump(tester, FakeAgentBackend(chatGptConnected: true, chatGptScopes: ['memories.read']));
    await tester.tap(find.text('Reconnect'));
    await settle(tester);
    expect(find.byKey(const ValueKey('connect_chatgpt_disconnect')), findsOneWidget);
    await shoot(tester, '3b-chatgpt-reconnect-sheet-disconnect');
  });

  testWidgets('4 agent prompt before copy', (tester) async {
    await pump(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    await shoot(tester, '4-agent-prompt');
  });

  testWidgets('5 agent prompt after copy', (tester) async {
    captureClipboard(tester);
    await pump(tester, FakeAgentBackend());
    await tester.tap(find.byKey(const ValueKey('connect_agent_instinct')));
    await settle(tester);
    await tester.tap(find.byKey(const ValueKey('agent_key_copy_prompt')));
    await settle(tester);
    await shoot(tester, '5-agent-prompt-copied');
  });

  testWidgets('6 active agent', (tester) async {
    await pump(tester, FakeAgentBackend(keys: {'Muse': DateTime.now().subtract(const Duration(hours: 2))}));
    await tester.tap(find.byKey(const ValueKey('connect_agent_muse')));
    await settle(tester);
    await shoot(tester, '6-active-agent');
  });

  testWidgets('7 ask about a conversation', (tester) async {
    final backend = FakeAgentBackend(chatGptConnected: true);
    await pump(
      tester,
      backend,
      home: Builder(
        builder: (context) => Scaffold(
          appBar: AppBar(leading: const OmiBackButton()),
          body: Center(
            child: OmiButton(
              key: const ValueKey('open_ask'),
              label: 'Ask',
              onPressed: () => showAskAgentSheet(context, _conversation(), service: backend.service()),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('open_ask')));
    await settle(tester);
    expect(find.byKey(const ValueKey('ask_agent_chatgpt')), findsOneWidget);
    await shoot(tester, '7-ask-about-conversation');
  });

  testWidgets('8 ask without ChatGPT offers Connect', (tester) async {
    final backend = FakeAgentBackend();
    await pump(
      tester,
      backend,
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: OmiButton(
              key: const ValueKey('open_ask'),
              label: 'Ask',
              onPressed: () => showAskAgentSheet(context, _conversation(), service: backend.service()),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('open_ask')));
    await settle(tester);
    expect(find.byKey(const ValueKey('ask_agent_chatgpt')), findsNothing);
    expect(find.byKey(const ValueKey('ask_agent_connect_chatgpt')), findsOneWidget);
    await shoot(tester, '8-ask-connect-first');
  });
}
