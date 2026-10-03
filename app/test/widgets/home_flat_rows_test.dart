/// Home's rows on the canvas are flat: a device tile at the start, the title, and a quiet second
/// line. A conversation, one still processing, a meeting that was not captured and what is
/// recording now all share the layout.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/capture_gap_list_item.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/device_tile.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

void main() {
  late ConversationProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
  });
  tearDown(() => provider.dispose());

  Future<void> pump(WidgetTester tester, Widget child) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: provider),
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: OmiCanvas(child: child)),
      ),
    ));
    await tester.pump();
  }

  DeviceTile tile(WidgetTester tester) => tester.widget<DeviceTile>(find.byType(DeviceTile));

  final started = DateTime(2026, 9, 20, 10, 5);
  ServerConversation conversation({ConversationStatus status = ConversationStatus.completed}) => ServerConversation(
        id: 'a',
        createdAt: started,
        startedAt: started,
        finishedAt: started.add(const Duration(minutes: 21)),
        structured: Structured('Design review', 'Overview', emoji: '🧠'),
        status: status,
        source: ConversationSource.phone,
      );

  testWidgets('a conversation: its device, the title and the time, flat on the page', (tester) async {
    final row = conversation();
    provider.conversations = [row];
    await pump(tester, ConversationListItem(conversation: row, date: DateTime(2026, 9, 20), conversationIdx: 0));

    expect(tile(tester).source, 'phone');
    expect(find.text('🧠'), findsNothing, reason: 'the tile replaces the emoji');
    expect(find.text('Design review'), findsOneWidget);
    expect(find.textContaining('10:05'), findsOneWidget);
    expect(find.textContaining('21'), findsNothing, reason: 'the length is on the conversation page');

    final card = tester.widget<AnimatedContainer>(find.byKey(const ValueKey('conversation_card')));
    expect((card.decoration! as BoxDecoration).color, OmiColors.canvas,
        reason: 'the page colour, so the swipe-delete button behind stays hidden');
    final tileRect = tester.getRect(find.byType(DeviceTile));
    expect(tileRect.left, OmiSpacing.md, reason: 'on the page gutter, in line with the day labels');
    final cardRect = tester.getRect(find.byKey(const ValueKey('conversation_card')));
    expect(tileRect.top - cardRect.top, DeviceTile.rowPadding, reason: 'air above and below each row');
  });

  testWidgets('processing: the same row, its device faded, "Processing" over the start time', (tester) async {
    await pump(tester, ProcessingConversationWidget(conversation: conversation(status: ConversationStatus.processing)));

    expect(tile(tester).source, 'phone');
    expect(tile(tester).faded, isTrue);
    expect(find.text('Processing'), findsOneWidget);
    expect(find.textContaining('10:05'), findsOneWidget);
  });

  testWidgets('not captured: an empty dashed tile, the meeting and its time, and nothing to tap', (tester) async {
    await pump(
      tester,
      CaptureGapListItem(
        gap: CalendarCaptureGap(
          eventId: 'evt-1',
          title: 'Design review with Priya',
          startTime: DateTime.parse('2026-08-18T19:30:00Z'),
          endTime: DateTime.parse('2026-08-18T20:00:00Z'),
        ),
      ),
    );

    expect(tile(tester).missing, isTrue);
    expect(tile(tester).icon, Icons.event_busy);
    expect(find.text('Design review with Priya'), findsOneWidget);
    expect(find.byType(InkWell), findsNothing);
  });

  testWidgets('recording now: a green dot while live, grey when paused; trouble marks the words', (tester) async {
    Future<Color?> dot({bool paused = false, String? explanation}) async {
      await pump(
        tester,
        LiveCaptureCard(
          source: 'omi',
          status: 'Listening',
          paused: paused,
          explanation: explanation,
          elapsed: const Duration(minutes: 12, seconds: 4),
          lastLine: 'so we ship the widgets Friday',
          onPauseToggle: () {},
        ),
      );
      return tile(tester).status;
    }

    expect(await dot(), OmiColors.success);
    expect(tile(tester).source, 'omi');
    expect(tester.getRect(find.textContaining('so we ship')).left,
        greaterThanOrEqualTo(tester.getRect(find.text('Listening')).left),
        reason: 'the transcript line sits under the text, clear of the tile');
    expect(await dot(paused: true), OmiColors.textTertiary);
    expect(await dot(explanation: 'The pendant disconnected.'), isNull, reason: 'no dot on the tile');
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget, reason: 'the warning sits beside the word');
  });

  testWidgets('Ask anything is plain text in sentence case on the glass, no icon', (tester) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: OmiCanvas(child: Center(child: HomeAskOmiButton(onTap: () {})))),
    ));
    final label = tester.widget<Text>(find.text('Ask anything'));
    expect(label.style!.fontSize, OmiType.callout.fontSize);
    expect(label.style!.fontWeight, FontWeight.w500, reason: 'medium, as in Omi v8');
    expect(label.maxLines, 1);
    expect(find.descendant(of: find.byType(HomeAskOmiButton), matching: find.byType(Icon)), findsNothing);
    expect(find.descendant(of: find.byType(HomeAskOmiButton), matching: find.byType(OmiGlass)), findsOneWidget);
  });

  testWidgets('light Home blends into a warm white toward the bottom; dark has no blend', (tester) async {
    // A fresh key each time, as a theme change rebuilds the app with the new palette.
    Future<void> pump() => tester.pumpWidget(
          MaterialApp(
            home: Scaffold(body: OmiCanvas(child: Stack(children: [HomeWarmBlend(key: UniqueKey())]))),
          ),
        );
    await pump();
    final box = tester.widget<DecoratedBox>(find.byKey(const ValueKey('home_warm_blend')));
    final gradient = (box.decoration as BoxDecoration).gradient! as LinearGradient;
    expect(gradient.stops, [0.62, 0.72, 0.82]);
    expect(Color.alphaBlend(gradient.colors.last, OmiColors.canvas),
        isSameColorAs(const Color(0xFFFAF8F4), threshold: 0.01));
    expect(gradient.colors.first.a, 0, reason: 'the top of the screen stays white');

    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = OmiPalette.light);
    await pump();
    expect(find.byKey(const ValueKey('home_warm_blend')), findsNothing);
  });

  testWidgets('the Ask anything row is laid out in light and in dark', (tester) async {
    // Home's bottom layers as in home/page.dart: a Stack inside the body's Stack, holding only the
    // fade, the blend and the floating row. With no blend (dark) it must not shrink to nothing.
    Future<void> pump(Brightness brightness) async {
      OmiColors.active = OmiColors.forBrightness(brightness);
      await tester.pumpWidget(
        MaterialApp(
          key: ValueKey(brightness),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(brightness: Brightness.light),
          darkTheme: buildOmiTheme(brightness: Brightness.dark),
          themeMode: brightness == Brightness.dark ? ThemeMode.dark : ThemeMode.light,
          home: Scaffold(
            body: OmiCanvas(
              child: Builder(
                builder: (context) => Stack(
                  children: [
                    const SizedBox.expand(),
                    Stack(
                      children: [
                        const HomeChatBarBackdrop(),
                        const HomeWarmBlend(),
                        Positioned(
                          left: 16,
                          right: 16,
                          bottom: homeChatBarOffset(context),
                          child: Row(children: [Expanded(child: HomeAskOmiButton(onTap: () {}))]),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    }

    addTearDown(() => OmiColors.active = OmiPalette.light);
    for (final brightness in Brightness.values) {
      await pump(brightness);
      final ask = tester.getRect(find.byType(HomeAskOmiButton));
      expect(ask.width, greaterThan(300), reason: '$brightness: the row spans the screen');
      expect(ask.bottom, lessThanOrEqualTo(600), reason: '$brightness: it sits at the bottom, on screen');
      expect(ask.top, greaterThan(400), reason: '$brightness: at the bottom, not the top');
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('turning the app dark takes the warm blend away from a Home already on screen', (tester) async {
    // As in main.dart: the palette is set above MaterialApp, and the navigator keeps its global key,
    // so Home stays mounted through the switch.
    final navigator = GlobalKey<NavigatorState>();
    Widget app(Brightness brightness) {
      OmiColors.active = OmiColors.forBrightness(brightness);
      return MaterialApp(
        navigatorKey: navigator,
        theme: buildOmiTheme(brightness: Brightness.light),
        darkTheme: buildOmiTheme(brightness: Brightness.dark),
        themeMode: brightness == Brightness.dark ? ThemeMode.dark : ThemeMode.light,
        builder: (context, child) => KeyedSubtree(key: ValueKey(brightness), child: child!),
        home: const Scaffold(body: OmiCanvas(child: Stack(children: [HomeChatBarBackdrop(), HomeWarmBlend()]))),
      );
    }

    addTearDown(() => OmiColors.active = OmiPalette.light);
    await tester.pumpWidget(app(Brightness.light));
    expect(find.byKey(const ValueKey('home_warm_blend')), findsOneWidget);

    await tester.pumpWidget(app(Brightness.dark));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('home_warm_blend')), findsNothing, reason: 'no warm tint in dark');
    // The fade under the floating row turns to the dark page too.
    final fade = tester.widget<DecoratedBox>(
        find.descendant(of: find.byType(HomeChatBarBackdrop), matching: find.byType(DecoratedBox)));
    final colors = ((fade.decoration as BoxDecoration).gradient! as LinearGradient).colors;
    expect(colors.last, isSameColorAs(OmiPalette.dark.canvas));

    await tester.pumpWidget(app(Brightness.light));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('home_warm_blend')), findsOneWidget, reason: 'back in light, it returns');
  });
}
