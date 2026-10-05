/// Home on the canvas: what is recording now is a flat row with its device tile, and in light mode the
/// page blends into a warm white toward the bottom, under the floating row.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
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

  testWidgets('the floating row is laid out in light and in dark', (tester) async {
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
                          child: const SizedBox(key: ValueKey('home_floating_row'), height: kHomeChatBarHeight),
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
      final ask = tester.getRect(find.byKey(const ValueKey('home_floating_row')));
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
