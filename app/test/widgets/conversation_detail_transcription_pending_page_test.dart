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

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../helpers/transcription_hold_wire.dart';

/// Set to write the legacy-page PR evidence (UI-Evidence) PNGs here.
const _evidence = String.fromEnvironment('OMI_Q12_EVIDENCE_DIR');
final _boundary = GlobalKey();

/// The page's MessageListener branch for REPROCESS_TRANSCRIPTION_PENDING and the Summary tab's
/// empty state, driven with the real held-recording wire copies (`../helpers/transcription_hold_wire.dart`)
/// and the real reprocess call answering 409 `transcription_pending`.
Future<(ConversationDetailProvider, AppLocalizations)> _pumpPage(
  WidgetTester tester,
  ServerConversation initial, {
  ServerConversation? fetched,
  ConversationTab tab = ConversationTab.summary,
}) async {
  final conversations = ConversationProvider(isSignedIn: () => false)
    ..conversations = [initial]
    ..groupedConversations = {
      conversationLocalDayKey(initial.createdAt): [initial],
    }
    ..conversationDetailsFetcherOverride = (_) async => fetched ?? initial;
  final apps = AppProvider();
  final detail = ConversationDetailProvider(
    reprocess: heldWireReprocess(409, heldReprocess409Body),
    fetchConversation: (_) async => fetched ?? initial,
  )..setProviders(apps, conversations);
  addTearDown(() {
    detail.dispose();
    conversations.dispose();
    apps.dispose();
  });
  await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider<AppProvider>.value(value: apps),
            ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (_) => PeopleProvider()),
            ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {},
              ),
            ),
          ],
          child: ConversationDetailPage(conversation: initial, initialTab: tab),
        ),
      )));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  final l10n = AppLocalizations.of(tester.element(find.byType(ConversationDetailPage)));
  return (detail, l10n);
}

/// Captures the page as it renders on an iPhone for the PR's UI evidence; a no-op in CI.
Future<void> _captureEvidence(WidgetTester tester, String name) async {
  if (_evidence.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_boundary));
    final image = await boundary.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    final dir = await Directory(_evidence).create(recursive: true);
    await File('${dir.path}/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
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
    '.SF UI Display'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
  var dir = File(Platform.resolvedExecutable).absolute.parent;
  for (var i = 0; i < 10 && dir.path != dir.parent.path; i++, dir = dir.parent) {
    final icons = File('${dir.path}/artifacts/material_fonts/MaterialIcons-Regular.otf');
    if (!icons.existsSync()) continue;
    final loader = FontLoader('MaterialIcons')
      ..addFont(Future.value(ByteData.sublistView(Uint8List.fromList(icons.readAsBytesSync()))));
    await loader.load();
    return;
  }
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

Future<void> _drain(WidgetTester tester) async {
  // Let any feedback timer run out before the test ends.
  await tester.pump(const Duration(seconds: 10));
  await tester.pumpWidget(const SizedBox());
}

/// Title text drawn at rest (the editable field underneath also holds the stored title).
Finder _shownTitle(String text) => find.byWidgetPredicate((w) => w is Text && w.data == text);

void main() {
  setUpAll(initHeldWireEnv);
  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    TranscriptionPendingConversations.reset();
  });
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
    TranscriptionPendingConversations.reset();
  });

  Future<void> expectNoticeOnly(WidgetTester tester, AppLocalizations l10n) async {
    expect(find.byKey(const Key('conversation_detail_transcription_pending')), findsOneWidget);
    // The notice is the only place the body appears: no duplicate message.
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.generateSummary), findsNothing);
    expect(find.text(l10n.retry), findsNothing);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    // The header no longer says "Couldn't transcribe" above a notice that the summary is coming.
    expect(_shownTitle(TranscriptionPendingConversations.serverHoldTitle), findsNothing);
  }

  testWidgets('legacy, opened from the Home row: after the 409 the tab shows the notice and no action', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    // The list row (a) opens the page; the detail read lands copy (b), which has no Home step.
    final (detail, l10n) = await _pumpPage(tester, heldListRow(), fetched: heldDetail());
    expect(await detail.refreshConversation(), isTrue);
    await _settle(tester);
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    await expectNoticeOnly(tester, l10n);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy, cached detail copy: Generate Summary gives way to the notice after the 409', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    if (_evidence.isNotEmpty) {
      await tester.runAsync(_loadEvidenceFonts);
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393 * 3, 852 * 3);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
      final previousPalette = OmiColors.active;
      OmiColors.active = OmiPalette.dark;
      addTearDown(() => OmiColors.active = previousPalette);
    }
    final (detail, l10n) = await _pumpPage(tester, heldDetail());
    // Before any answer the server copy alone offers Generate Summary under its stand-in title.
    expect(find.text(l10n.generateSummary), findsOneWidget);
    expect(_shownTitle(TranscriptionPendingConversations.serverHoldTitle), findsOneWidget);
    await tester.tap(find.text(l10n.generateSummary));
    await _settle(tester);
    expect(TranscriptionPendingConversations.contains(heldConversationId), isTrue);
    await expectNoticeOnly(tester, l10n);
    await _captureEvidence(tester, '001-mobile-ios-legacy-detail-transcription-pending');
    debugDefaultTargetPlatformOverride = null;
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy, Transcript tab open: it says so once, not as an error', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, heldDetail(), tab: ConversationTab.transcript);
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy: a pending answer for another conversation says nothing here', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, heldDetail(), tab: ConversationTab.transcript);
    detail.lastFailedReprocessConversationId = 'another-conversation';
    detail.notifyInfo('REPROCESS_TRANSCRIPTION_PENDING');
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsNothing);
    await _drain(tester);
  });

  testWidgets('redesign: the Summary card explains it in place with no extra message', (tester) async {
    SummaryGenerationV2Gate.debugOverride = true;
    final (detail, l10n) = await _pumpPage(tester, heldListRow(), fetched: heldDetail());
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingTitle), findsOneWidget);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    TranscriptionPendingConversations.reset();
  });
}
