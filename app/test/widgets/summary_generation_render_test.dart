import 'dart:async';
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

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../helpers/summary_fixtures.dart';

/// Summary generation redesign, rendered with the real widgets in the dark palette.
/// `--dart-define=OMI_SUMMARY_UX_EVIDENCE_DIR=<dir>` writes 393×852 @3x PNGs.
const _evidence = String.fromEnvironment('OMI_SUMMARY_UX_EVIDENCE_DIR');

const _paulGraham = 'pg';

void _noop() {}

class _Case {
  const _Case(this.slug, this.setUp, {this.sheet = false, this.title = summaryFixtureTitle});

  final String slug;
  final bool sheet;
  final String title;

  /// Brings the provider (and the sheet's fetches) into the state to render.
  final Future<void> Function(ConversationDetailProvider provider, SummaryTemplateFetches fetches) setUp;
}

App get _pgApp => summaryApp(_paulGraham, 'Paul Graham');

Future<void> _fail(ConversationDetailProvider provider, {String? appId}) =>
    provider.reprocessConversation(appId: appId);

final _results = <String, ReprocessResult>{
  '08-failure-template': const ReprocessFailed(statusCode: 502),
  '09-failure-busy': const ReprocessBusy(),
  '10-failure-limit': const ReprocessRateLimited(),
};

final _cases = <_Case>[
  _Case('01-empty-state', (p, f) async {}),
  _Case('02-sheet-omi-and-template', sheet: true, (p, f) async {
    f.enabled.single.complete([_pgApp]);
    f.suggested.single.complete([]);
  }),
  _Case('03-sheet-loading', sheet: true, (p, f) async {}),
  _Case('04-sheet-error', sheet: true, (p, f) async {
    f.enabled.single.completeError(StateError('offline'));
    f.suggested.single.complete([]);
  }),
  _Case('05-sheet-empty', sheet: true, (p, f) async {
    f.enabled.single.complete([]);
    f.suggested.single.complete([]);
  }),
  _Case('06-generating', (p, f) async {
    unawaited(p.reprocessConversation(appId: _paulGraham));
  }),
  _Case('07-result-chips', (p, f) async {}),
  _Case('08-failure-template', (p, f) => _fail(p, appId: _paulGraham)),
  _Case('09-failure-busy', (p, f) => _fail(p)),
  _Case('10-failure-limit', (p, f) => _fail(p)),
  _Case(
    '11-empty-state-long-title',
    (p, f) async {},
    title: 'Turn right at the next one, not this one, then the second left after the bakery on Valencia '
        'and park behind the blue building near the old theater',
  ),
];

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().lastUsedSummarizationAppId = _paulGraham;
    SummaryGenerationV2Gate.debugOverride = true;
  });
  tearDown(() => SummaryGenerationV2Gate.debugOverride = null);

  for (final item in _cases) {
    testWidgets('summary generation renders ${item.slug}', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      tester.view.physicalSize = const Size(393 * 3, 852 * 3);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final previousPalette = OmiColors.active;
      OmiColors.active = OmiPalette.dark;
      addTearDown(() => OmiColors.active = previousPalette);
      if (_evidence.isNotEmpty) await tester.runAsync(_loadEvidenceFonts);

      final gate = Completer<ReprocessResult>();
      final fetches = SummaryTemplateFetches();
      final conversation = item.slug == '07-result-chips'
          ? summaryConversation(
              overview: 'Directions to the café: second light after the gas station, then left on Valencia.',
              appResults: [
                AppResponse(
                  '## The real lesson\n\nMost wrong turns come from acting on the first plausible option. '
                  'The second light was the right one, and the first was a dead end into a garage.\n\n'
                  '- Wait for the confirming signal\n- Name the landmark, not the count',
                  appId: _paulGraham,
                ),
              ],
            )
          : summaryConversation(title: item.title);
      final provider = summaryProvider(
        conversation,
        fetches: fetches,
        catalog: [_pgApp],
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) {
          final result = _results[item.slug];
          return result == null ? gate.future : Future.value(result);
        },
      );
      addTearDown(provider.dispose);
      final folders = FolderProvider(foldersFetcher: () async => []);
      addTearDown(folders.dispose);
      final tabs = TabController(length: 2, vsync: const TestVSync());
      addTearDown(tabs.dispose);

      const boundaryKey = ValueKey('summary-generation-evidence');
      await tester.pumpWidget(
        RepaintBoundary(
          key: boundaryKey,
          child: MultiProvider(
            providers: [
              ChangeNotifierProvider<ConversationDetailProvider>.value(value: provider),
              ChangeNotifierProvider<FolderProvider>.value(value: folders),
            ],
            child: MaterialApp(
              locale: const Locale('en'),
              theme: buildOmiTheme(brightness: Brightness.dark).copyWith(platform: TargetPlatform.iOS),
              debugShowCheckedModeBanner: false,
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: Scaffold(
                backgroundColor: OmiPalette.dark.surface0,
                appBar: AppBar(
                  automaticallyImplyLeading: false,
                  leading: const Center(child: OmiBackButton.circled()),
                ),
                body: Column(
                  children: [
                    ConversationDetailHeader(onOpenRecordings: (_) {}),
                    ConversationDetailTabs(controller: tabs, onTap: (_) {}),
                    const Expanded(
                      child: CustomScrollView(
                        slivers: [
                          SliverPadding(
                            padding: EdgeInsets.fromLTRB(OmiSpacing.md, 18, OmiSpacing.md, 0),
                            sliver: GetAppsWidgets(onOpenTranscript: _noop),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      if (_evidence.isNotEmpty) {
        // Decode the Omi mark before capture; test image decoding is asynchronous.
        await tester.runAsync(() => precacheImage(
              AssetImage(Assets.images.herologo.path),
              tester.element(find.byType(GetAppsWidgets)),
            ));
        await tester.pump();
      }

      if (item.sheet) {
        unawaited(showSummarizedAppsSheet(tester.element(find.byType(GetAppsWidgets))));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 600));
      }
      await item.setUp(provider, fetches);
      for (var i = 0; i < 4; i++) {
        await tester.pump(const Duration(milliseconds: 300));
      }
      expect(tester.takeException(), isNull);

      final l10n = summaryL10n(tester);
      switch (item.slug) {
        case '01-empty-state' || '11-empty-state-long-title':
          expect(find.text(l10n.summaryWithOmi), findsOneWidget);
        case '02-sheet-omi-and-template':
          expect(find.text('Paul Graham'), findsOneWidget);
          expect(find.text(l10n.lastUsedLabel), findsOneWidget);
        case '03-sheet-loading':
          expect(find.byKey(const Key('summary_template_skeleton')), findsNWidgets(2));
        case '04-sheet-error':
          expect(find.text(l10n.summaryTemplatesLoadFailed), findsOneWidget);
        case '05-sheet-empty':
          expect(find.text(l10n.summaryNoTemplatesYet), findsOneWidget);
        case '06-generating':
          expect(find.text(l10n.summarySummarizingWith('Paul Graham')), findsOneWidget);
        case '07-result-chips':
          expect(find.byKey(const Key('summary_source_chips')), findsOneWidget);
        case '08-failure-template':
          expect(find.text(l10n.summaryTemplateFailedTitle('Paul Graham')), findsOneWidget);
        case '09-failure-busy':
          expect(find.text(l10n.summaryBusyTitle), findsOneWidget);
        case '10-failure-limit':
          expect(find.text(l10n.summaryLimitTitle), findsOneWidget);
      }

      if (_evidence.isNotEmpty) {
        await tester.runAsync(() async {
          final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
          final image = await boundary.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          final dir = await Directory(_evidence).create(recursive: true);
          await File('${dir.path}/${item.slug}.png').writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      if (!gate.isCompleted) gate.complete(const ReprocessBusy());
      await tester.pump();
      debugDefaultTargetPlatformOverride = null;
    });
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
