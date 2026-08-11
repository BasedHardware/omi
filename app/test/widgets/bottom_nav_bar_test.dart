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
}

Finder _findIcon(FaIconData icon) => find.byWidgetPredicate((widget) => widget is FaIcon && widget.icon == icon.data);

Color _colorFor(WidgetTester tester, FaIconData icon) => tester.widget<FaIcon>(_findIcon(icon)).color!;
