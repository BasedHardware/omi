import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/home_tab_switcher.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

Future<void> _pumpSwitcher(WidgetTester tester, HomeProvider provider, void Function(int, bool) onTabTap) {
  return tester.pumpWidget(
    ChangeNotifierProvider<HomeProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: HomeTabSwitcher(onTabTap: onTabTap)),
      ),
    ),
  );
}

void main() {
  test('HomeProvider preserves selection callback and notification semantics', () {
    final provider = HomeProvider();
    addTearDown(provider.dispose);

    var notificationCount = 0;
    final callbackIndices = <int>[];
    provider.addListener(() => notificationCount++);
    provider.onSelectedIndexChanged = callbackIndices.add;

    provider.setIndex(HomeProvider.tasksTab);
    provider.setIndex(HomeProvider.tasksTab);

    expect(provider.selectedIndex, HomeProvider.tasksTab);
    expect(callbackIndices, [HomeProvider.tasksTab, HomeProvider.tasksTab]);
    expect(notificationCount, 2);
  });

  test('the shell has exactly two pages: Home and Tasks', () {
    expect(HomeProvider.homeTab, 0);
    expect(HomeProvider.tasksTab, 1);
    expect(HomeProvider.tabCount, 2);
  });

  testWidgets('the switcher reports a tap and a repeat tap', (tester) async {
    final provider = HomeProvider();
    addTearDown(provider.dispose);
    final taps = <(int, bool)>[];
    await _pumpSwitcher(tester, provider, (index, isRepeat) {
      taps.add((index, isRepeat));
      provider.setIndex(index);
    });

    await tester.tap(find.byKey(OmiKeys.homeTabTasks));
    await tester.pump();
    await tester.tap(find.byKey(OmiKeys.homeTabTasks));
    await tester.pump();
    await tester.tap(find.byKey(OmiKeys.homeTabHome));
    await tester.pump();

    expect(taps, [(HomeProvider.tasksTab, false), (HomeProvider.tasksTab, true), (HomeProvider.homeTab, false)]);
  });

  testWidgets('announces both pages as buttons with the selected one marked', (tester) async {
    final semantics = tester.ensureSemantics();
    final provider = HomeProvider();
    addTearDown(provider.dispose);
    await _pumpSwitcher(tester, provider, (_, __) {});

    final home = tester.getSemantics(find.bySemanticsLabel('Home')).getSemanticsData();
    expect(home.flagsCollection.isButton, isTrue);
    expect(home.flagsCollection.isSelected.toBoolOrNull(), isTrue);
    expect(home.hasAction(SemanticsAction.tap), isTrue);
    final tasks = tester.getSemantics(find.bySemanticsLabel('Tasks')).getSemanticsData();
    expect(tasks.flagsCollection.isSelected.toBoolOrNull(), isFalse);
    expect(find.bySemanticsLabel('Conversations'), findsNothing, reason: 'Conversations is part of Home now');
    expect(find.bySemanticsLabel('Apps'), findsNothing, reason: 'Apps lives under Settings › Integrations');
    semantics.dispose();
  });

  testWidgets('keeps the chat bar and page clearances tied to the system inset', (tester) async {
    late double chatBarOffset;
    late double clearance;
    late double chatClearance;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(viewPadding: EdgeInsets.only(bottom: 34)),
        child: Builder(
          builder: (context) {
            chatBarOffset = homeChatBarOffset(context);
            clearance = homeBottomClearance(context);
            chatClearance = homeChatBarClearance(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    // The chat bar floats just above the home indicator, never over it.
    expect(chatBarOffset, 34 + kHomeChatBarBottomGap);
    // Pages without the chat bar scroll clear of the inset.
    expect(clearance, 34 + kHomeScrollEndPadding);
    // Home content clears the chat bar that floats above the inset.
    expect(chatClearance, greaterThan(chatBarOffset + kHomeChatBarHeight));
  });

  testWidgets('reserves viewPadding, which a keyboard does not collapse', (tester) async {
    // The home Scaffold sets resizeToAvoidBottomInset: false, so an open keyboard leaves the
    // system bar where it was while driving padding.bottom to zero. Pin that the shell reads
    // viewPadding: padding is zero here and only viewPadding is set.
    late double inset;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(viewPadding: EdgeInsets.only(bottom: 48)),
        child: Builder(
          builder: (context) {
            inset = homeBottomInset(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(inset, 48);
  });
}
