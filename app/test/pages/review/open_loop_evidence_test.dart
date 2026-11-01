import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

import '../../helpers/sfpro_font_fixtures.dart';

// Renders the Review page with two open-loop cards beside one review question,
// in light and dark, and after a Remind-me-later answer. The layout assertions
// run everywhere; with --dart-define=OPEN_LOOP_EVIDENCE_OUTPUT=<dir> the PNGs
// used as PR evidence are written there too.
const _cards = [
  OpenLoopCard(
    cardId: 'ol-1',
    date: '2026-10-26',
    question: 'Did Maya send the vendor write-up?',
    contextLine: "From Monday's Pricing sync, due Tuesday",
  ),
  OpenLoopCard(
    cardId: 'ol-2',
    date: '2026-10-26',
    question: 'Did you send Tyler the bullets for the Stably write-up? (your task from Thu)',
    contextLine: "From Thursday's Stably sync, no follow-up since Friday",
  ),
];

const _task = ReviewItem(
  itemId: 'task:c1',
  kind: ReviewItemKind.task,
  task: TaskItem(candidateId: 'c1', description: 'Send the signed SOW'),
);

ReviewProvider _provider() => ReviewProvider(
      isEligible: () => true,
      reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
      loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [_task], remainingToday: 1)),
      loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: _cards)),
      sendOpenLoopAnswer: (card, action) async =>
          ApiSuccess(OpenLoopAnswerResult(cardId: card.cardId, state: action.wire)),
    );

/// On a phone the app bar title uses the system font; the test engine's default
/// is a placeholder face, so the evidence theme names SF Pro for it.
ThemeData _evidenceTheme(Brightness brightness) {
  final theme = buildOmiTheme(brightness: brightness);
  return theme.copyWith(
    appBarTheme: theme.appBarTheme.copyWith(
      titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
  );
}

Widget _host(ReviewProvider provider, Brightness brightness) {
  OmiColors.active = OmiColors.forBrightness(brightness);
  return ChangeNotifierProvider<ReviewProvider>.value(
    value: provider,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: _evidenceTheme(brightness),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: RepaintBoundary(
        key: const Key('open_loop_evidence'),
        child: ReviewPage(probeDreamReport: () async => false),
      ),
    ),
  );
}

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
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadFonts);
  const output = String.fromEnvironment('OPEN_LOOP_EVIDENCE_OUTPUT');
  const frame = Key('open_loop_evidence');

  Future<void> writeFrame(WidgetTester tester, String name) async {
    if (output.isEmpty) return;
    await tester.runAsync(() async {
      final render = tester.renderObject<RenderRepaintBoundary>(find.byKey(frame));
      final image = await render.toImage(pixelRatio: 2);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  // Fixed pumps, not pumpAndSettle: the evidence write runs on the real clock.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    await tester.pump(const Duration(milliseconds: 120));
  }

  Future<void> pumpReview(WidgetTester tester, Brightness brightness) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = _provider();
    await provider.load();
    await tester.pumpWidget(_host(provider, brightness));
    await settle(tester);
  }

  testWidgets('Review with open-loop cards, light', (tester) async {
    await pumpReview(tester, Brightness.light);
    expect(tester.takeException(), isNull);
    expect(find.text('Did Maya send the vendor write-up?'), findsOneWidget);
    expect(find.text('Did you send Tyler the bullets for the Stably write-up? (your task from Thu)'), findsOneWidget);
    expect(find.text('Done'), findsNWidgets(2));
    expect(find.text('Remind me later'), findsNWidgets(2));
    expect(find.text('Drop it'), findsNWidgets(2));
    await writeFrame(tester, '001-mobile-ios-review-open-loops-light');
  });

  testWidgets('Review with open-loop cards, dark', (tester) async {
    await pumpReview(tester, Brightness.dark);
    expect(tester.takeException(), isNull);
    expect(find.text('Did Maya send the vendor write-up?'), findsOneWidget);
    expect(find.text('Did you send Tyler the bullets for the Stably write-up? (your task from Thu)'), findsOneWidget);
    await writeFrame(tester, '002-mobile-ios-review-open-loops-dark');
  });

  testWidgets('Review after Remind me later on the first card', (tester) async {
    await pumpReview(tester, Brightness.dark);
    await tester.tap(find.text('Remind me later').first);
    await settle(tester);
    expect(tester.takeException(), isNull);
    expect(find.text('Did Maya send the vendor write-up?'), findsNothing, reason: 'answered; leaves at once');
    expect(find.text('Did you send Tyler the bullets for the Stably write-up? (your task from Thu)'), findsOneWidget);
    await writeFrame(tester, '003-mobile-ios-review-open-loops-reminded');
  });
}
