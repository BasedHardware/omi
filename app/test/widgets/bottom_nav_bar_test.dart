import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';

void main() {
  test('HomeProvider preserves selection callback and notification semantics', () {
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    var notificationCount = 0;
    final callbackIndices = <int>[];
    provider.addListener(() => notificationCount++);
    provider.onSelectedIndexChanged = callbackIndices.add;

    provider.setIndex(2);
    provider.setIndex(2);

    expect(provider.selectedIndex, 2);
    expect(callbackIndices, [2, 2]);
    expect(notificationCount, 2);
  });

  testWidgets('updates selection and detects a repeat tap before rebuilding', (tester) async {
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    final taps = <(int, bool)>[];
    final warmups = <int>[];
    await _pumpBar(
      tester,
      provider,
      BottomNavBar(
        onTabWarmup: warmups.add,
        onTabTap: (index, isRepeat) {
          taps.add((index, isRepeat));
          provider.setIndex(index);
        },
      ),
    );

    expect(_glyphFor(tester, 0).asset, 'assets/icons/tab-today-fill.svg');
    expect(_glyphFor(tester, 0).color, OmiColors.textPrimary);
    expect(_glyphFor(tester, 2).color, OmiColors.dockTabIdle);

    provider.setIndex(2);
    await tester.pump();

    expect(_glyphFor(tester, 0).asset, 'assets/icons/tab-today.svg');
    expect(_glyphFor(tester, 0).color, OmiColors.dockTabIdle);
    expect(_glyphFor(tester, 2).color, OmiColors.textPrimary);

    provider.setIndex(0);
    await tester.pump();

    await tester.tap(find.byKey(const Key('bottom_nav_tab_2')));
    await tester.tap(find.byKey(const Key('bottom_nav_tab_2')));

    expect(taps, [(2, false), (2, true)]);
    expect(warmups, [2, 2]);
  });

  testWidgets('announces each tab once, by its name, with its selected state', (tester) async {
    final semantics = tester.ensureSemantics();
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    await _pumpBar(tester, provider, BottomNavBar(onTabTap: (_, __) {}));

    // The design's app map: Today · Conversations · To do · Apps (devices live in Settings).
    for (final label in ['Today', 'Conversations', 'To do', 'Apps']) {
      expect(find.bySemanticsLabel(label), findsOneWidget, reason: 'the $label tab is announced exactly once');
    }
    final home = tester.getSemantics(find.bySemanticsLabel('Today')).getSemanticsData();
    expect(home.flagsCollection.isButton, isTrue);
    expect(home.flagsCollection.isSelected.toBoolOrNull(), isTrue);
    expect(home.hasAction(SemanticsAction.tap), isTrue);
    final tasks = tester.getSemantics(find.bySemanticsLabel('To do')).getSemanticsData();
    expect(tasks.flagsCollection.isSelected.toBoolOrNull(), isFalse);
    semantics.dispose();
  });

  testWidgets('the Ask button opens chat and is only shown when there is somewhere to go', (tester) async {
    final semantics = tester.ensureSemantics();
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    await _pumpBar(tester, provider, BottomNavBar(onTabTap: (_, __) {}));
    expect(find.byKey(const Key('bottom_nav_ask')), findsNothing);

    var asked = 0;
    await _pumpBar(tester, provider, BottomNavBar(onTabTap: (_, __) {}, onAskTap: () => asked++));
    expect(find.bySemanticsLabel('Ask Omi'), findsOneWidget);
    final ask = tester.getRect(find.byKey(const Key('bottom_nav_ask')));
    expect(ask.width, greaterThanOrEqualTo(OmiSize.minTap));
    expect(ask.height, greaterThanOrEqualTo(OmiSize.minTap));
    await tester.tap(find.byKey(const Key('bottom_nav_ask')));
    expect(asked, 1);
    semantics.dispose();
  });

  testWidgets('holding the Omi mark for two seconds opens Memories; a tap still asks', (tester) async {
    final semantics = tester.ensureSemantics();
    final provider = HomeProvider();
    addTearDown(provider.dispose);
    var asked = 0;
    var held = 0;
    await _pumpBar(
      tester,
      provider,
      BottomNavBar(onTabTap: (_, __) {}, onAskTap: () => asked++, onAskHold: () => held++),
    );
    final mark = find.byKey(const Key('bottom_nav_ask'));

    // A short press is still Ask, however long it takes to lift under two seconds.
    await tester.longPressAt(tester.getCenter(mark)); // the default long press is ~0.5 s
    await tester.pump();
    expect(held, 0, reason: 'half a second is not the hidden gesture');
    expect(asked, 1, reason: 'a press released before two seconds is a tap: Ask');

    final gesture = await tester.startGesture(tester.getCenter(mark));
    await tester.pump(kAskHoldDuration + const Duration(milliseconds: 50));
    await gesture.up();
    await tester.pump();
    expect(held, 1);

    // Screen readers cannot discover a hidden hold, so Memories is a named action on the mark.
    expect(
      tester.getSemantics(find.bySemanticsLabel('Ask Omi')),
      isSemantics(customActions: const [CustomSemanticsAction(label: 'Memories')]),
    );
    expect(asked, 1, reason: 'the hold did not also ask');
    semantics.dispose();
  });

  testWidgets('open Ask covers the whole screen: the header and floating buttons sit under the blur', (tester) async {
    final provider = HomeProvider();
    addTearDown(provider.dispose);
    var header = 0;
    var newTask = 0;
    final asked = <String>[];
    await tester.pumpWidget(
      ChangeNotifierProvider<HomeProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            appBar: AppBar(actions: [
              IconButton(key: const Key('header_button'), onPressed: () => header++, icon: const Icon(Icons.search)),
            ]),
            body: Stack(children: [
              const SizedBox.expand(), // the page under the dock, as Home's tabs are
              BottomNavBar(onTabTap: (_, __) {}, onAskTap: () {}, onAskSubmit: asked.add),
              // A floating action placed above the dock, as To do's New Task is.
              Positioned(
                left: 16,
                right: 16,
                bottom: 140,
                child: TextButton(
                  key: const Key('new_task_button'),
                  onPressed: () => newTask++,
                  child: const Text('New Task'),
                ),
              ),
            ]),
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('bottom_nav_ask')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('bottom_nav_ask_field')), findsOneWidget);
    expect(find.byKey(const Key('bottom_nav_ask_scrim')), findsOneWidget);
    expect(find.byType(BackdropFilter), findsWidgets, reason: 'everything behind the question blurs');

    // Taps meant for the header or the floating button land on the scrim, which closes Ask.
    await tester.tap(find.byKey(const Key('new_task_button')), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(newTask, 0);
    expect(find.byKey(const Key('bottom_nav_ask_field')), findsNothing, reason: 'the scrim closed Ask');

    await tester.tap(find.byKey(const Key('bottom_nav_ask')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('header_button')), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(header, 0);

    // Closed again, the page is reachable as before and the dock is back in place.
    await tester.tap(find.byKey(const Key('header_button')));
    expect(header, 1);
    expect(find.byKey(const Key('bottom_nav_ask')), findsOneWidget);
  });

  testWidgets('a thumb that drifts a little still holds; one that slides away does nothing', (tester) async {
    final provider = HomeProvider();
    addTearDown(provider.dispose);
    var asked = 0;
    var held = 0;
    await _pumpBar(
      tester,
      provider,
      BottomNavBar(onTabTap: (_, __) {}, onAskTap: () => asked++, onAskHold: () => held++),
    );
    final center = tester.getCenter(find.byKey(const Key('bottom_nav_ask')));

    final drifting = await tester.startGesture(center);
    await tester.pump(const Duration(milliseconds: 600));
    await drifting.moveBy(const Offset(0, -20)); // past the arena's 18 pt slop
    await tester.pump(kAskHoldDuration);
    await drifting.up();
    await tester.pump();
    expect(held, 1, reason: 'a hold survives a small drift');
    expect(asked, 0);

    final sliding = await tester.startGesture(center);
    await tester.pump(const Duration(milliseconds: 300));
    await sliding.moveBy(const Offset(-60, 0));
    await tester.pump(kAskHoldDuration);
    await sliding.up();
    await tester.pump();
    expect(held, 1, reason: 'sliding off is not a hold');
    expect(asked, 0, reason: 'nor a tap');
  });

  testWidgets('floats in the home-indicator area but never behind an opaque system bar', (tester) async {
    for (final (inset, expectedOffset) in [(0.0, 8.0), (34.0, 25.0), (48.0, 56.0)]) {
      final layout = await _layoutForBottomInset(tester, viewPadding: inset, padding: inset);
      expect(
        layout.screenBottom - layout.capsule.bottom,
        moreOrLessEquals(expectedOffset, epsilon: 0.5),
        reason: 'with a ${inset}pt inset the capsule sits ${expectedOffset}pt above the edge',
      );
      expect(layout.capsule.height, moreOrLessEquals(kBottomNavRowHeight, epsilon: 0.5));
      for (final entry in layout.tapTargets.entries) {
        expect(entry.value.height, greaterThanOrEqualTo(OmiSize.minTap), reason: '${entry.key} target height');
        expect(entry.value.width, greaterThanOrEqualTo(OmiSize.minTap), reason: '${entry.key} target width');
      }
    }
  });

  testWidgets('keeps the floating slot and page clearances tied to the bar geometry', (tester) async {
    late double offset;
    late double chatBarOffset;
    late double clearance;
    late double chatClearance;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(viewPadding: EdgeInsets.only(bottom: 34)),
        child: Builder(
          builder: (context) {
            offset = bottomNavBarBottomOffset(context);
            chatBarOffset = bottomNavChatBarOffset(context);
            clearance = bottomNavBarClearance(context);
            chatClearance = homeChatBarClearance(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    // What floats above the bar sits above the capsule, never over it.
    expect(chatBarOffset, greaterThanOrEqualTo(offset + kBottomNavRowHeight));
    // Scrolling content clears the whole capsule.
    expect(clearance, greaterThan(offset + kBottomNavRowHeight));
    // Home content clears the slot that floats above the bar.
    expect(chatClearance, greaterThan(chatBarOffset + kHomeChatBarHeight));
  });

  testWidgets('reserves viewPadding, which a keyboard does not collapse', (tester) async {
    // The home Scaffold sets resizeToAvoidBottomInset: false, so an open keyboard leaves the
    // system bar exactly where it was while driving padding.bottom to zero. Reading padding
    // instead of viewPadding would put the bar back under the navigation bar in precisely this
    // state, so pin the distinction: padding is zero here and only viewPadding is set.
    const systemNavBarHeight = 48.0;

    final keyboardOpen = await _layoutForBottomInset(tester, viewPadding: systemNavBarHeight, padding: 0);

    expect(keyboardOpen.capsule.bottom, lessThanOrEqualTo(keyboardOpen.screenBottom - systemNavBarHeight));
  });
}

Future<void> _pumpBar(WidgetTester tester, HomeProvider provider, Widget bar) {
  return tester.pumpWidget(
    ChangeNotifierProvider<HomeProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: bar),
      ),
    ),
  );
}

OmiGlyph _glyphFor(WidgetTester tester, int index) => tester.widget<OmiGlyph>(
      find.descendant(of: find.byKey(Key('bottom_nav_tab_$index')), matching: find.byType(OmiGlyph)),
    );

/// Pumps the bar under the given bottom [viewPadding] and [padding] and reports where the capsule
/// and its tap targets landed. The two insets are separate so a test can pin which one the bar
/// reads.
Future<({double screenBottom, Rect capsule, Map<String, Rect> tapTargets})> _layoutForBottomInset(
  WidgetTester tester, {
  required double viewPadding,
  required double padding,
}) async {
  final provider = HomeProvider();
  addTearDown(provider.dispose);

  await tester.pumpWidget(
    ChangeNotifierProvider<HomeProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              viewPadding: EdgeInsets.only(bottom: viewPadding),
              padding: EdgeInsets.only(bottom: padding),
            ),
            child: Scaffold(
              body: BottomNavBar(key: ValueKey('$viewPadding/$padding'), onTabTap: (_, __) {}),
            ),
          ),
        ),
      ),
    ),
  );

  return (
    screenBottom: tester.getRect(find.byType(Scaffold)).bottom,
    capsule: tester.getRect(find.byType(OmiGlass).first),
    tapTargets: {
      for (final (index, label) in const [(0, 'Today'), (1, 'Conversations'), (2, 'To do'), (3, 'Apps')])
        label: tester.getRect(find.byKey(Key('bottom_nav_tab_$index'))),
    },
  );
}
