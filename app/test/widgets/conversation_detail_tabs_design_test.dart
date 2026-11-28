import 'package:flutter/material.dart';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/ui/ui.dart';

/// The Summary / Transcript tabs: an underline on a full-width hairline in the standard design;
/// capsules, the open one filled, in the experimental design.
void main() {
  tearDown(() => ExperimentalDesign.debugOverride = null);

  Future<void> pumpTabs(WidgetTester tester, {required bool experimental}) async {
    ExperimentalDesign.debugOverride = experimental;
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: DefaultTabController(
          length: 2,
          child: Builder(
            builder: (context) => Scaffold(
              body: ConversationDetailTabs(
                controller: DefaultTabController.of(context),
                onTap: (_) {},
                showVisibility: false,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Color hairlineColor(WidgetTester tester) {
    final box = tester.widget<DecoratedBox>(
      find.descendant(of: find.byType(ConversationDetailTabs), matching: find.byType(DecoratedBox)).first,
    );
    return ((box.decoration as BoxDecoration).border! as Border).bottom.color;
  }

  Color? inkOf(WidgetTester tester, String label) => DefaultTextStyle.of(tester.element(find.text(label))).style.color;

  const summary = Key('conversation_tab_summary');
  const transcript = Key('conversation_tab_transcript');

  testWidgets('standard design: underline on a full-width hairline', (tester) async {
    await pumpTabs(tester, experimental: false);
    expect(hairlineColor(tester), ConversationDetailInk.hairline);
    expect(tester.widget<TabBar>(find.byType(TabBar)).indicator, isA<UnderlineTabIndicator>());
    expect(inkOf(tester, 'Summary'), OmiColors.textPrimary);
  });

  testWidgets('experimental design: capsules, the open one filled, same bar height', (tester) async {
    await pumpTabs(tester, experimental: false);
    final standardHeight = tester.getSize(find.byType(ConversationDetailTabs)).height;

    await pumpTabs(tester, experimental: true);
    expect(tester.getSize(find.byType(ConversationDetailTabs)).height, standardHeight);
    expect(hairlineColor(tester), Colors.transparent);

    final tabBar = tester.widget<TabBar>(find.byType(TabBar));
    final fill = tabBar.indicator as ShapeDecoration;
    expect(fill.color, OmiColors.textPrimary);
    expect(fill.shape, isA<StadiumBorder>());

    // Each tab holds a 34 pt capsule with a hairline edge; the two do not touch.
    for (final key in [summary, transcript]) {
      final capsule = find.descendant(of: find.byKey(key), matching: find.byType(Container));
      expect(tester.getSize(capsule).height, 34);
      final decoration = tester.widget<Container>(capsule).decoration! as BoxDecoration;
      expect(decoration.borderRadius, OmiRadius.pillAll);
    }
    final summaryCapsule = find.descendant(of: find.byKey(summary), matching: find.byType(Container));
    final transcriptCapsule = find.descendant(of: find.byKey(transcript), matching: find.byType(Container));
    expect(tester.getRect(transcriptCapsule).left - tester.getRect(summaryCapsule).right, 8);

    // Each capsule leads with a glyph in the label's ink.
    expect(
        find.descendant(of: find.byKey(summary), matching: find.byIcon(Icons.auto_awesome_outlined)), findsOneWidget);
    expect(find.descendant(of: find.byKey(transcript), matching: find.byIcon(Icons.notes)), findsOneWidget);

    // The fill is exactly the open tab's capsule.
    final bar = tester.getRect(find.byType(TabBar));
    final inset = tabBar.indicatorPadding.resolve(TextDirection.ltr);
    final open = tester.getRect(summaryCapsule);
    expect(bar.top + inset.top, open.top);
    expect(bar.bottom - inset.bottom, open.bottom);

    // The open tab's label is in the page colour, the other in the chips' ink.
    expect(inkOf(tester, 'Summary'), OmiColors.surface0);
    expect(inkOf(tester, 'Transcript'), ConversationDetailInk.words);

    await tester.tap(find.byKey(transcript));
    await tester.pumpAndSettle();
    expect(inkOf(tester, 'Transcript'), OmiColors.surface0);
    expect(inkOf(tester, 'Summary'), ConversationDetailInk.words);
  });
}
