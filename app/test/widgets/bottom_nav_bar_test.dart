import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

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

  testWidgets('keeps the tab row clear of the system navigation bar inset', (tester) async {
    // A 3-button Android navigation bar is roughly this tall and fully opaque.
    const systemNavBarHeight = 48.0;

    final withoutInset = await _layoutForBottomInset(tester, 0);
    final withInset = await _layoutForBottomInset(tester, systemNavBarHeight);

    final safeBottom = withInset.screenBottom - systemNavBarHeight;
    for (final entry in withInset.iconBottoms.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(safeBottom),
        reason: 'the ${entry.key} tab must not be drawn behind the system navigation bar',
      );
    }

    // The row lifts by exactly the reported inset, so a device that reports no
    // bottom inset keeps today's layout.
    for (final label in withoutInset.iconBottoms.keys) {
      expect(
        withoutInset.iconBottoms[label]! - withInset.iconBottoms[label]!,
        moreOrLessEquals(systemNavBarHeight),
        reason: 'the ${label} tab should lift by the bottom inset',
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

/// Pumps the bar under a bottom view padding of [bottomInset] and reports where
/// the tab icons landed relative to the bottom of the screen.
Future<({double screenBottom, Map<String, double> iconBottoms})> _layoutForBottomInset(
  WidgetTester tester,
  double bottomInset,
) async {
  final provider = HomeProvider();
  addTearDown(provider.dispose);

  await tester.pumpWidget(
    ChangeNotifierProvider<HomeProvider>.value(
      value: provider,
      child: MaterialApp(
        home: Builder(
          builder: (context) => MediaQuery(
            // viewPadding is what survives a keyboard; the home Scaffold sets
            // resizeToAvoidBottomInset: false, so that is the inset the bar
            // has to respect.
            data: MediaQuery.of(context).copyWith(
              viewPadding: EdgeInsets.only(bottom: bottomInset),
              padding: EdgeInsets.only(bottom: bottomInset),
            ),
            child: Scaffold(
              body: BottomNavBar(onTabTap: (_, __) {}),
            ),
          ),
        ),
      ),
    ),
  );

  return (
    screenBottom: tester.getRect(find.byType(Scaffold)).bottom,
    iconBottoms: {
      for (final (label, icon) in _tabIcons) label: tester.getRect(_findIcon(icon)).bottom,
    },
  );
}

Finder _findIcon(FaIconData icon) => find.byWidgetPredicate((widget) => widget is FaIcon && widget.icon == icon.data);

Color _colorFor(WidgetTester tester, FaIconData icon) => tester.widget<FaIcon>(_findIcon(icon)).color!;
