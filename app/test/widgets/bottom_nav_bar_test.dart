import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/home_provider.dart';
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
    await tester.pumpWidget(
      ChangeNotifierProvider<HomeProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: BottomNavBar(
              onTabWarmup: warmups.add,
              onTabTap: (index, isRepeat) {
                taps.add((index, isRepeat));
                provider.setIndex(index);
              },
            ),
          ),
        ),
      ),
    );

    expect(_colorFor(tester, FontAwesomeIcons.house), Colors.white);
    expect(_colorFor(tester, FontAwesomeIcons.listCheck), Colors.grey);

    provider.setIndex(2);
    await tester.pump();

    expect(_colorFor(tester, FontAwesomeIcons.house), Colors.grey);
    expect(_colorFor(tester, FontAwesomeIcons.listCheck), Colors.white);

    provider.setIndex(0);
    await tester.pump();

    await tester.tap(_findIcon(FontAwesomeIcons.listCheck));
    await tester.tap(_findIcon(FontAwesomeIcons.listCheck));

    expect(taps, [(2, false), (2, true)]);
    expect(warmups, [2, 2]);
  });

  testWidgets('announces each icon-only tab to screen readers', (tester) async {
    final semantics = tester.ensureSemantics();
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<HomeProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: BottomNavBar(onTabTap: (_, __) {})),
        ),
      ),
    );

    for (final label in ['Home', 'Conversations', 'Tasks', 'Apps']) {
      expect(find.bySemanticsLabel(label), findsOneWidget, reason: 'the $label tab has no visible text');
    }
    final home = tester.getSemantics(find.bySemanticsLabel('Home')).getSemanticsData();
    expect(home.flagsCollection.isButton, isTrue);
    expect(home.flagsCollection.isSelected.toBoolOrNull(), isTrue);
    expect(home.hasAction(SemanticsAction.tap), isTrue);
    final tasks = tester.getSemantics(find.bySemanticsLabel('Tasks')).getSemanticsData();
    expect(tasks.flagsCollection.isSelected.toBoolOrNull(), isFalse);
    semantics.dispose();
  });

  testWidgets('keeps the tab row clear of the system navigation bar inset', (tester) async {
    // A 3-button Android navigation bar is roughly this tall and fully opaque.
    const systemNavBarHeight = 48.0;

    final withoutInset = await _layoutForBottomInset(tester, viewPadding: 0, padding: 0);
    final withInset = await _layoutForBottomInset(
      tester,
      viewPadding: systemNavBarHeight,
      padding: systemNavBarHeight,
    );

    final safeBottom = withInset.screenBottom - systemNavBarHeight;
    for (final entry in withInset.iconBottoms.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(safeBottom),
        reason: 'the ${entry.key} tab must not be drawn behind the system navigation bar',
      );
    }

    // The row lifts by exactly the reported inset: the inset is reserved once,
    // never scaled or stacked on a second allowance.
    for (final label in withoutInset.iconBottoms.keys) {
      expect(
        withoutInset.iconBottoms[label]! - withInset.iconBottoms[label]!,
        moreOrLessEquals(systemNavBarHeight, epsilon: 0.5),
        reason: 'the $label tab should lift by the bottom inset',
      );
    }
  });

  testWidgets('sits directly on the system inset instead of stacking its own gap on top', (tester) async {
    // iPhone home-indicator inset. The bar used to keep ~27pt of empty space
    // under its icons and then add the inset below that, leaving the icons
    // ~74pt above the screen edge. A platform tab bar puts its content row
    // straight on the inset: UITabBar is a 49pt row above the 34pt safe area
    // (Apple HIG, Tab bars / Layout), Material bottom navigation a 56dp row.
    const homeIndicatorInset = 34.0;

    for (final inset in [0.0, homeIndicatorInset, 48.0]) {
      final layout = await _layoutForBottomInset(tester, viewPadding: inset, padding: inset);
      final safeBottom = layout.screenBottom - inset;

      for (final entry in layout.tapTargets.entries) {
        final target = entry.value;
        expect(
          target.bottom,
          moreOrLessEquals(safeBottom, epsilon: 0.5),
          reason: 'the ${entry.key} tap target should end exactly where the ${inset}pt inset begins',
        );
        expect(
          target.height,
          inInclusiveRange(48.0, 56.0),
          reason: 'the ${entry.key} row should be a platform-sized tab row, at least a 48dp target',
        );
        expect(target.width, greaterThanOrEqualTo(48.0));
      }

      for (final entry in layout.iconBottoms.entries) {
        expect(
          safeBottom - entry.value,
          inInclusiveRange(8.0, 16.0),
          reason: 'the ${entry.key} icon should sit just above the inset, not float over a second gap',
        );
      }

      expect(layout.barHeight, moreOrLessEquals(kBottomNavBarHeight + inset, epsilon: 0.5));
    }
  });

  testWidgets('keeps the chat bar and page clearances tied to the row geometry', (tester) async {
    late double chatBarOffset;
    late double clearance;
    late double chatClearance;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(viewPadding: EdgeInsets.only(bottom: 34)),
        child: Builder(
          builder: (context) {
            chatBarOffset = bottomNavChatBarOffset(context);
            clearance = bottomNavBarClearance(context);
            chatClearance = homeChatBarClearance(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    // The chat bar floats above the tappable row, never over it.
    expect(chatBarOffset, greaterThanOrEqualTo(34 + kBottomNavRowHeight));
    // Scrolling content clears the whole bar, fade and inset included.
    expect(clearance, 34 + kBottomNavBarHeight);
    // Home content clears the chat bar that floats above the row.
    expect(chatClearance, greaterThan(chatBarOffset + kHomeChatBarHeight));
  });

  testWidgets('reserves viewPadding, which a keyboard does not collapse', (tester) async {
    // The home Scaffold sets resizeToAvoidBottomInset: false, so an open
    // keyboard leaves the system bar exactly where it was while driving
    // padding.bottom to zero. Reading padding instead of viewPadding would put
    // the tab row back under the navigation bar in precisely this state, so
    // pin the distinction rather than the value: padding is zero here and only
    // viewPadding is set.
    const systemNavBarHeight = 48.0;

    final keyboardOpen = await _layoutForBottomInset(
      tester,
      viewPadding: systemNavBarHeight,
      padding: 0,
    );

    final safeBottom = keyboardOpen.screenBottom - systemNavBarHeight;
    for (final entry in keyboardOpen.iconBottoms.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(safeBottom),
        reason: 'the ${entry.key} tab must reserve viewPadding, not padding',
      );
    }
  });
}

final _tabIcons = <(String, FaIconData)>[
  ('Home', FontAwesomeIcons.house),
  ('Conversations', FontAwesomeIcons.comments),
  ('Tasks', FontAwesomeIcons.listCheck),
  ('Apps', FontAwesomeIcons.puzzlePiece),
];

/// Pumps the bar under the given bottom [viewPadding] and [padding] and reports
/// where the tab icons landed relative to the bottom of the screen. The two are
/// separate so a test can pin which inset the bar actually reads.
Future<({double screenBottom, double barHeight, Map<String, double> iconBottoms, Map<String, Rect> tapTargets})>
    _layoutForBottomInset(
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
            // viewPadding is what survives a keyboard; the home Scaffold sets
            // resizeToAvoidBottomInset: false, so that is the inset the bar
            // has to respect.
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
    barHeight:
        tester.getRect(find.descendant(of: find.byType(BottomNavBar), matching: find.byType(Container)).first).height,
    iconBottoms: {
      for (final (label, icon) in _tabIcons) label: tester.getRect(_findIcon(icon)).bottom,
    },
    tapTargets: {
      for (final (label, icon) in _tabIcons)
        label: tester.getRect(find.ancestor(of: _findIcon(icon), matching: find.byType(InkWell)).first),
    },
  );
}

Finder _findIcon(FaIconData icon) => find.byWidgetPredicate((widget) => widget is FaIcon && widget.icon == icon.data);

Color _colorFor(WidgetTester tester, FaIconData icon) => tester.widget<FaIcon>(_findIcon(icon)).color!;
