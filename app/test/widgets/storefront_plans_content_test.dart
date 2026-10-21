import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/pages/settings/widgets/plans/storefront_plans_content.dart';
import 'package:omi/ui/ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> fixture([String name = 'plus_monthly_yearly_toggle']) =>
    jsonDecode(File('test/fixtures/storefront_v2/$name.json').readAsStringSync()) as Map<String, dynamic>;

const evidence = String.fromEnvironment('OMI_STOREFRONT_UI_EVIDENCE_DIR');
const boundaryKey = Key('storefront_evidence');

Future<void> capture(WidgetTester tester, String name) async {
  if (evidence.isEmpty) return;
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  InlineSpan productFont(InlineSpan span) {
    if (span is! TextSpan) return span;
    final style = span.style ?? const TextStyle();
    return TextSpan(
      text: span.text,
      // Keep package icon fonts intact: copying their already-qualified fontFamily
      // would apply the package prefix a second time.
      style: style.fontFamily == null ? style.copyWith(fontFamily: 'SF Pro Display') : style,
      children: span.children?.map(productFont).toList(),
      recognizer: span.recognizer,
      semanticsLabel: span.semanticsLabel,
      locale: span.locale,
    );
  }

  for (final element in find.byType(RichText).evaluate()) {
    final paragraph = element.renderObject;
    if (paragraph is RenderParagraph) paragraph.text = productFont(paragraph.text);
  }
  void repaint(RenderObject object) {
    object.visitChildren(repaint);
    object.markNeedsPaint();
  }

  repaint(tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey)));
  await tester.pump();
  await tester.runAsync(() async {
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(evidence).create(recursive: true);
    await File('$evidence/$name').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Future<void> pumpSheet(
  WidgetTester tester, {
  PlanStorefront? data,
  bool loading = false,
  bool failed = false,
  bool dark = true,
  Size size = const Size(390, 844),
  double scale = 1,
  Widget? content,
  String? title = 'Plans',
  PlanType? livePlan,
  bool cancelScheduled = false,
  Future<void> Function(StorefrontTier, StorefrontPrice)? select,
  VoidCallback? retry,
  VoidCallback? manage,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final previousPalette = OmiColors.active;
  addTearDown(() => OmiColors.active = previousPalette);
  OmiColors.active = dark ? OmiPalette.dark : OmiPalette.light;
  await tester.runAsync(() async {
    final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
    for (final entry in fonts) {
      final loader = FontLoader(entry['family'] as String);
      for (final font in entry['fonts'] as List<dynamic>) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
    for (final family in [
      'Roboto',
      'CupertinoSystemText',
      'CupertinoSystemDisplay',
      '.SF UI Text',
      '.SF UI Display',
      'FlutterTest',
      'Ahem'
    ]) {
      final loader = FontLoader(family)
        ..addFont(rootBundle.load('assets/fonts/SFPRODISPLAYREGULAR.OTF'))
        ..addFont(rootBundle.load('assets/fonts/SFPRODISPLAYMEDIUM.OTF'));
      await loader.load();
    }
  });
  final sheet = content ??
      StorefrontPlansContent(
        storefront: data,
        loading: loading,
        failed: failed,
        livePlan: livePlan,
        cancelScheduled: cancelScheduled,
        onRetry: () async => retry?.call(),
        onManage: () async => manage?.call(),
        onSelect: select ?? (_, __) async {},
      );
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pumpWidget(MaterialApp(
    key: UniqueKey(),
    debugShowCheckedModeBanner: false,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: buildOmiTheme(brightness: dark ? Brightness.dark : Brightness.light).copyWith(
      platform: TargetPlatform.iOS,
      textTheme: buildOmiTheme(brightness: dark ? Brightness.dark : Brightness.light)
          .textTheme
          .apply(fontFamily: 'SF Pro Display'),
    ),
    builder: (context, child) =>
        MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: child!),
    home: RepaintBoundary(
      key: boundaryKey,
      child: Scaffold(
        body: Align(
          alignment: title == null ? Alignment.topCenter : Alignment.bottomCenter,
          child: title == null ? sheet : OmiSheetScaffold(title: title, padding: EdgeInsets.zero, child: sheet),
        ),
      ),
    ),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  test('budget dismissal persists for the server period and only the current account', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().uid = 'fixture-a';
    expect(BudgetNudgeDismissal.isDismissed('2026-10'), isFalse);
    await BudgetNudgeDismissal.dismiss('2026-10');
    expect(BudgetNudgeDismissal.isDismissed('2026-10'), isTrue);
    expect(BudgetNudgeDismissal.isDismissed('2026-11'), isFalse);
    SharedPreferencesUtil().uid = 'fixture-b';
    expect(BudgetNudgeDismissal.isDismissed('2026-10'), isFalse);
    expect(BudgetNudgeDismissal.isDismissed(null), isFalse);
    expect(BudgetNudgeDismissal.isDismissed(''), isFalse);
  });

  testWidgets('monthly sheet is one header, one current line, and deck card copy', (tester) async {
    String? selectedId;
    final data = PlanStorefront.fromJson(fixture());
    await pumpSheet(tester, data: data, select: (_, price) async => selectedId = price.id);
    expect(find.text('Plans'), findsOneWidget);
    expect(find.text('Choose your plan'), findsOneWidget);
    expect(find.text(r"You're on Plus · $19.99/mo · renews Nov 1"), findsOneWidget);
    expect(find.text('Yearly · 2 months free'), findsOneWidget);
    expect(find.text('Recommended'), findsOneWidget);
    expect(find.text('Your plan'), findsOneWidget);
    expect(find.text(r'$49.99/month'), findsOneWidget);
    expect(find.text(r'$19.99/month'), findsWidgets);
    expect(find.text(r'$16.66/month'), findsNothing);
    expect(find.text(r'$199.90 billed yearly · 2 months free'), findsOneWidget);
    expect(find.text(r'Switch to yearly · save $39.98'), findsOneWidget);
    expect(find.text('Upgrade to Pro'), findsOneWidget);
    expect(find.text('Renews monthly until you cancel. Cancel anytime in settings.'), findsOneWidget);
    expect(find.text('About 280 hours of recording a month, enough to wear it all day'), findsOneWidget);
    expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('storefront_tier_plus')), matching: find.textContaining('•')),
        findsNothing);
    expect(find.byKey(const Key('storefront_restore')), findsNothing);
    expect(find.text('Refresh'), findsNothing);
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    expect(find.text(r'$41.66/month'), findsOneWidget);
    expect(find.text(r'$499.90 billed yearly · 2 months free'), findsOneWidget);
    expect(find.text('Renews yearly until you cancel. Cancel anytime in settings.'), findsWidgets);
    expect(find.text(r'Switch to yearly · save $39.98'), findsOneWidget);
    expect(
      find.descendant(of: find.byKey(const Key('storefront_tier_plus')), matching: find.text(r'$19.99/month')),
      findsOneWidget,
    );
    await tester.ensureVisible(find.byKey(const Key('storefront_buy_operator')));
    await tester.tap(find.byKey(const Key('storefront_buy_operator')).hitTestable());
    await tester.pumpAndSettle();
    expect(selectedId, 'price_operator_year');
    expect(tester.takeException(), isNull);
  });

  testWidgets('see all plans stays collapsed until opened', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()));
    expect(find.text('See all plans'), findsOneWidget);
    expect(find.byKey(const Key('storefront_tier_basic')), findsNothing);
    expect(find.byKey(const Key('storefront_tier_architect')), findsNothing);
    expect(find.byKey(const Key('storefront_tier_plus')), findsOneWidget);
    expect(find.byKey(const Key('storefront_tier_operator')), findsOneWidget);
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_other_plans')), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byKey(const Key('storefront_other_plans')).hitTestable());
    await tester.pumpAndSettle();
    final list = tester.widget<ListView>(find.byKey(const Key('storefront_scroll')));
    final children = (list.childrenDelegate as SliverChildListDelegate).children;
    final pro = children.indexWhere((child) => child.key == const Key('storefront_tier_operator'));
    final plus = children.indexWhere((child) => child.key == const Key('storefront_tier_plus'));
    final architect = children.indexWhere((child) => child.key == const Key('storefront_tier_architect'));
    expect(pro, greaterThanOrEqualTo(0));
    expect(plus, greaterThan(pro));
    expect(architect, greaterThan(plus));
    expect(find.byKey(const Key('storefront_tier_basic')), findsNothing);
    final scrollable =
        find.descendant(of: find.byKey(const Key('storefront_scroll')), matching: find.byType(Scrollable));
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_tier_architect')), 80, scrollable: scrollable);
    await tester.pumpAndSettle();
    final position = tester.state<ScrollableState>(scrollable).position;
    final viewTop = tester.getTopLeft(scrollable).dy;
    final plusTop = tester.getTopLeft(find.byKey(const Key('storefront_tier_plus'))).dy;
    position.jumpTo((position.pixels + plusTop - viewTop).clamp(0.0, position.maxScrollExtent));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty and error use deck copy and only the error offers Try again', (tester) async {
    var retried = false;
    var managed = false;
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture()..['tiers'] = []),
        retry: () => retried = true,
        manage: () => managed = true);
    expect(find.text("Plans aren't available right now. Try again in a minute."), findsOneWidget);
    expect(find.widgetWithText(OmiButton, 'Try again'), findsNothing);
    expect(find.byKey(const Key('storefront_restore')), findsNothing);
    await capture(tester, '016-mobile-ios-empty.png');
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_manage')), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byKey(const Key('storefront_manage')).hitTestable());
    await tester.pump();
    expect(managed, isTrue);

    await pumpSheet(tester, failed: true, retry: () => retried = true, manage: () => managed = true);
    expect(find.text("Couldn't load plans. Check your connection and try again."), findsOneWidget);
    await capture(tester, '017-mobile-ios-error.png');
    await tester.tap(find.text('Try again').hitTestable());
    await tester.pump();
    expect(retried, isTrue);
    expect(find.byType(OmiCloseButton).hitTestable(), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('legacy view is the current line, the note, and manage billing', (tester) async {
    for (final name in ['legacy_unlimited', 'legacy_neo']) {
      final data = PlanStorefront.fromJson(fixture(name));
      await pumpSheet(tester, data: data);
      expect(find.text('Your plan'), findsWidgets);
      expect(find.text(data.current!.line), findsOneWidget);
      expect(find.text("We don't sell this plan anymore, but yours stays exactly as it is."), findsOneWidget);
      expect(find.text('Manage billing'), findsOneWidget);
      expect(find.byKey(const Key('storefront_restore')), findsNothing);
      expect(find.text('Refresh'), findsNothing);
      expect(find.byKey(const Key('storefront_year')), findsNothing);
      expect(
          find.byWidgetPredicate((widget) =>
              widget.key is ValueKey<String> && (widget.key as ValueKey<String>).value.startsWith('storefront_buy_')),
          findsNothing);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('each golden renders its header and backend strings', (tester) async {
    const shots = {
      'architect_settings': '001-mobile-ios-architect-settings.png',
      'cancel_scheduled_plus': '002-mobile-ios-cancel-scheduled-plus.png',
      'free_budget80': '003-mobile-ios-free-budget-80.png',
      'free_mcp_cap': '004-mobile-ios-free-mcp-cap.png',
      'free_pro_gate_proactive': '005-mobile-ios-free-pro-gate-proactive.png',
      'free_pro_gate_screen': '006-mobile-ios-free-pro-gate-screen.png',
      'free_settings': '007-mobile-ios-free-settings.png',
      'legacy_unlimited': '008-mobile-ios-legacy-unlimited.png',
      'legacy_neo': '018-mobile-ios-legacy-neo.png',
      'plus_annual_current': '009-mobile-ios-plus-annual-current.png',
      'plus_budget80': '010-mobile-ios-plus-budget-80.png',
      'plus_monthly_yearly_toggle': '011-mobile-ios-plus-monthly-yearly-toggle.png',
      'pro_settings': '012-mobile-ios-pro-settings.png',
      'pro_budget_cap': '019-mobile-ios-pro-budget-cap.png',
      'cancel_scheduled_pro': '020-mobile-ios-cancel-scheduled-pro.png',
    };
    const showYearlyCta = {'architect_settings', 'plus_monthly_yearly_toggle', 'pro_settings', 'pro_budget_cap'};
    for (final entry in shots.entries) {
      final data = PlanStorefront.fromJson(fixture(entry.key));
      await pumpSheet(tester, data: data);
      expect(find.text(data.header), findsOneWidget);
      expect(find.text(data.current!.line), findsOneWidget);
      expect(data.tiers.where((tier) => tier.isCurrent).every((tier) => tier.bullets.isEmpty), isTrue);
      if (data.current?.legacy != true) {
        for (final tier in data.tiers.where((tier) => tier.isCurrent)) {
          expect(
            find.descendant(of: find.byKey(Key('storefront_tier_${tier.planId}')), matching: find.textContaining('•')),
            findsNothing,
            reason: entry.key,
          );
        }
      }
      if (entry.key == 'free_mcp_cap') {
        final card = find.byKey(const Key('storefront_tier_plus'));
        final texts = find
            .descendant(of: card, matching: find.byType(Text))
            .evaluate()
            .map((element) => (element.widget as Text).data ?? '')
            .toList();
        final hours = texts.indexWhere((value) => value.contains('hours'));
        final mcp = texts.indexWhere((value) => value.contains('MCP requests'));
        expect(hours, greaterThanOrEqualTo(0));
        expect(mcp, greaterThan(hours));
      }
      if (entry.key == 'cancel_scheduled_plus') {
        expect(find.text('Upgrade to Pro'), findsNothing);
        expect(find.text(r'Switch to yearly · save $39.98'), findsNothing);
        expect(find.text('Recommended'), findsNothing);
        expect(find.text('Resubscribe'), findsOneWidget);
        expect(find.text('Resubscribe first to change plans'), findsWidgets);
        expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
        expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
        expect(find.byKey(const Key('storefront_tier_basic')), findsOneWidget);
        expect(find.byKey(const Key('storefront_blocked_basic')), findsOneWidget);
        expect(find.descendant(of: find.byKey(const Key('storefront_tier_basic')), matching: find.textContaining('•')),
            findsNothing);
        expect(find.text(r'$0'), findsOneWidget);
        expect(find.byKey(const Key('storefront_month')), findsNothing);
        expect(find.byKey(const Key('storefront_year')), findsNothing);
        expect(data.yearlyToggleLabel, isNull);
        expect(
          tester.getTopLeft(find.byKey(const Key('storefront_tier_plus'))).dy,
          lessThan(tester.getTopLeft(find.byKey(const Key('storefront_tier_operator'))).dy),
        );
        expect(find.descendant(of: find.byKey(const Key('storefront_tier_plus')), matching: find.textContaining('•')),
            findsNothing);
      }
      if (entry.key == 'cancel_scheduled_pro') {
        expect(find.text('Resubscribe'), findsOneWidget);
        expect(find.text('Upgrade to Architect'), findsNothing);
        expect(find.text('Recommended'), findsNothing);
        expect(find.byKey(const Key('storefront_blocked_basic')), findsOneWidget);
        expect(find.byKey(const Key('storefront_buy_operator')), findsOneWidget);
        expect(
          tester.getTopLeft(find.byKey(const Key('storefront_tier_operator'))).dy,
          lessThan(tester.getTopLeft(find.byKey(const Key('storefront_tier_basic'))).dy),
        );
        final scrollable =
            find.descendant(of: find.byKey(const Key('storefront_scroll')), matching: find.byType(Scrollable));
        await tester.scrollUntilVisible(find.byKey(const Key('storefront_blocked_plus')), 80, scrollable: scrollable);
        await tester.scrollUntilVisible(find.byKey(const Key('storefront_blocked_architect')), 80,
            scrollable: scrollable);
        expect(find.byKey(const Key('storefront_buy_architect')), findsNothing);
        await tester.scrollUntilVisible(find.text(data.header), -800, scrollable: scrollable);
      }
      if (entry.key == 'pro_budget_cap') {
        expect(find.text("You've used all of this month's usage"), findsOneWidget);
        expect(find.text('Upgrade to Architect'), findsOneWidget);
        expect(find.text('Recommended'), findsOneWidget);
        expect(find.byKey(const Key('storefront_buy_architect')), findsOneWidget);
        expect(find.byKey(const Key('storefront_tier_basic')), findsNothing);
      }
      if (entry.key == 'pro_settings') {
        expect(find.byKey(const Key('storefront_tier_architect')), findsNothing);
        expect(find.text('Upgrade to Architect'), findsNothing);
      }
      if (entry.key == 'free_settings') {
        expect(find.text('Get Plus'), findsOneWidget);
        expect(find.text(r'$0'), findsOneWidget);
        expect(find.descendant(of: find.byKey(const Key('storefront_tier_basic')), matching: find.textContaining('•')),
            findsNothing);
      }
      if (showYearlyCta.contains(entry.key)) {
        await tester.tap(find.byKey(const Key('storefront_year')));
        await tester.pumpAndSettle();
        expect(find.textContaining('Switch to yearly · save'), findsOneWidget);
      }
      await capture(tester, entry.value);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('banner is one nudge line with See plans and Not now', (tester) async {
    var opened = false;
    final data = PlanStorefront.fromJson(fixture('plus_budget80'));
    await pumpSheet(tester,
        title: null,
        size: const Size(390, 132),
        content: BudgetUpsellCard(data: data, onOpen: () async => opened = true));
    expect(find.byKey(const Key('budget_80')), findsOneWidget);
    expect(find.text("You've used 80% of this month's usage · resets Nov 1"), findsOneWidget);
    expect(find.text('See plans'), findsOneWidget);
    expect(find.text('Not now'), findsOneWidget);
    expect(find.text('Usage'), findsNothing);
    await capture(tester, '013-mobile-ios-banner.png');
    await tester.tap(find.byKey(const Key('budget_nudge_compare')));
    await tester.pumpAndSettle();
    expect(opened, isTrue);
    expect(tester.getSize(find.byKey(const Key('budget_80'))).height, lessThan(180));
    await tester.tap(find.byKey(const Key('budget_nudge_dismiss')));
    await tester.pump();
    expect(find.byKey(const Key('budget_80')), findsNothing);
    for (final percent in [79, 100, 120]) {
      final json = fixture('plus_budget80');
      json['usage']['percent'] = percent;
      await pumpSheet(tester,
          title: null, content: BudgetUpsellCard(data: PlanStorefront.fromJson(json), onOpen: () async {}));
      expect(find.byKey(const Key('budget_80')), findsNothing);
    }
    await pumpSheet(tester,
        title: null,
        content: BudgetUpsellCard(data: PlanStorefront.fromJson(fixture('legacy_unlimited')), onOpen: () async {}));
    expect(find.byKey(const Key('budget_80')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('usage meter is the backend line without a title row', (tester) async {
    final usage = PlanStorefront.fromJson(fixture('plus_budget80')).usage!;
    await pumpSheet(tester, title: null, size: const Size(390, 90), content: StorefrontUsageMeter(usage: usage));
    expect(find.text('80% used · about 20 hours of recording left · resets Nov 1'), findsOneWidget);
    expect(find.text('Usage'), findsNothing);
    expect(find.byKey(const Key('storefront_usage_meter_bar')), findsOneWidget);
    final cardBottom = tester.getBottomLeft(find.byKey(const Key('storefront_usage_meter'))).dy;
    final barBottom = tester.getBottomLeft(find.byKey(const Key('storefront_usage_meter_bar'))).dy;
    expect(cardBottom - barBottom, lessThanOrEqualTo(OmiSpacing.md + 1));
    await capture(tester, '014-mobile-ios-meter.png');
    expect(tester.takeException(), isNull);
  });

  testWidgets('a new period restores a dismissed nudge', (tester) async {
    final data = PlanStorefront.fromJson(fixture('plus_budget80'));
    await pumpSheet(tester, title: null, content: BudgetUpsellCard(data: data, onOpen: () async {}));
    await tester.tap(find.byKey(const Key('budget_nudge_dismiss')));
    await tester.pump();
    expect(find.byKey(const Key('budget_80')), findsNothing);
    final json = fixture('plus_budget80');
    json['usage']['period_id'] = '2026-11';
    await pumpSheet(tester,
        title: null, content: BudgetUpsellCard(data: PlanStorefront.fromJson(json), onOpen: () async {}));
    expect(find.byKey(const Key('budget_80')), findsOneWidget);
  });

  testWidgets('small light phone keeps the recommended action on screen', (tester) async {
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture('free_settings')), dark: false, size: const Size(320, 568));
    final action = find.byKey(const Key('storefront_buy_plus'));
    expect(action.hitTestable(), findsOneWidget);
    expect(tester.getBottomRight(action).dy, lessThanOrEqualTo(568));
    expect(tester.getSize(action).height, greaterThanOrEqualTo(44));
    expect(find.byType(OmiCloseButton).hitTestable(), findsOneWidget);
    await capture(tester, '015-mobile-ios-small-phone-light.png');
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture('free_settings')), dark: false, size: const Size(320, 568), scale: 1.6);
    await tester.drag(find.byKey(const Key('storefront_scroll')), const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  for (final dark in [true, false]) {
    testWidgets('real draggable sheet keeps Pro price and CTA above the small-phone fold (dark=$dark)', (tester) async {
      await pumpSheet(tester, dark: dark, size: const Size(320, 568), content: const SizedBox.shrink());
      final data = PlanStorefront.fromJson(fixture());
      final closed = showOmiSheet<void>(
        context: tester.element(find.byType(Scaffold)),
        title: 'Plans',
        padding: EdgeInsets.zero,
        builder: (_) => StorefrontPlansContent(
          storefront: data,
          onRetry: () async {},
          onSelect: (_, __) async {},
          onManage: () async {},
        ),
      );
      await tester.pumpAndSettle();
      final content = find.byType(StorefrontPlansContent);
      final route = ModalRoute.of(tester.element(content))! as OmiSheetRoute<void>;
      expect(route.enableDrag, isTrue);
      expect(route.showDragHandle, isTrue);
      expect(tester.getTopLeft(content).dy, lessThan(568 * 0.2));
      for (final key in ['storefront_price_operator', 'storefront_buy_operator']) {
        final control = find.byKey(Key(key));
        expect(control.hitTestable(), findsOneWidget);
        expect(tester.getBottomRight(control).dy, lessThanOrEqualTo(568));
      }
      final close = find.byType(OmiCloseButton).last;
      expect(close.hitTestable(), findsOneWidget);
      expect(tester.getSize(close).height, greaterThanOrEqualTo(44));
      expect(tester.takeException(), isNull);
      await tester.tap(close);
      await tester.pumpAndSettle();
      await closed;
      expect(find.byType(StorefrontPlansContent), findsNothing);
    });
  }

  testWidgets('annual current price has no monthly buy button', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture('plus_annual_current')), livePlan: PlanType.plus);
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    expect(find.byKey(const Key('storefront_buy_operator')), findsOneWidget);
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a live unlimited plan and an unknown plan hide buy buttons', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()), livePlan: PlanType.unlimitedV2);
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    final unknown = fixture();
    unknown['current']['plan_id'] = 'future_desktop';
    await pumpSheet(tester, data: PlanStorefront.fromJson(unknown), livePlan: PlanType.unknown('future_desktop'));
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('hidden storefront never renders offers or actions', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()..['show_subscription_ui'] = false));
    expect(find.byKey(const Key('storefront_tier_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_manage')), findsNothing);
  });

  testWidgets('cancel scheduled offers only Resubscribe and tells other tiers to resubscribe first', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture('cancel_scheduled_plus')));
    expect(find.text('Your Plus plan ends Nov 1'), findsOneWidget);
    expect(find.text(r"You're on Plus · $19.99/mo"), findsOneWidget);
    expect(find.text('Upgrade to Pro'), findsNothing);
    expect(find.text('Upgrade to Architect'), findsNothing);
    expect(find.text('Recommended'), findsNothing);
    expect(find.byKey(const Key('storefront_month')), findsNothing);
    expect(find.byKey(const Key('storefront_year')), findsNothing);
    expect(find.text('Resubscribe'), findsOneWidget);
    expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_blocked_operator')), findsOneWidget);
    expect(find.byKey(const Key('storefront_tier_basic')), findsOneWidget);
    expect(find.byKey(const Key('storefront_blocked_basic')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('storefront_tier_basic')), matching: find.textContaining('•')),
        findsNothing);
    expect(find.text('Resubscribe first to change plans'), findsWidgets);
    final current = find.byKey(const Key('storefront_tier_plus'));
    expect(find.descendant(of: current, matching: find.textContaining('•')), findsNothing);
    expect(
      find.descendant(
        of: current,
        matching: find.text('Renews monthly until you cancel. Cancel anytime in settings.'),
      ),
      findsOneWidget,
    );
    expect(find.descendant(of: find.byKey(const Key('storefront_tier_operator')), matching: find.textContaining('•')),
        findsWidgets);
    final scrollable =
        find.descendant(of: find.byKey(const Key('storefront_scroll')), matching: find.byType(Scrollable));
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_blocked_architect')), 80, scrollable: scrollable);
    expect(find.byKey(const Key('storefront_buy_architect')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('transcription usage legacy hides checkout buttons', (tester) async {
    final json = fixture();
    json['usage']['kind'] = 'transcription';
    await pumpSheet(tester, data: PlanStorefront.fromJson(json));
    expect(find.byKey(const Key('storefront_buy_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing);
    expect(find.text('Upgrade to Pro'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('same-tier yearly CTA is the backend price label, not a computed saving', (tester) async {
    final json = fixture();
    (json['tiers'] as List).cast<Map<String, dynamic>>().firstWhere((tier) => tier['plan_id'] == 'plus')['cta_label'] =
        'Get Plus';
    await pumpSheet(tester, data: PlanStorefront.fromJson(json));
    expect(find.text('Get Plus'), findsNothing);
    expect(find.text(r'Switch to yearly · save $39.98'), findsOneWidget);
    expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    expect(find.text(r'Switch to yearly · save $39.98'), findsOneWidget);
    expect(find.text('Get Plus'), findsNothing);
    expect(find.text('Your plan'), findsOneWidget);
    final current = find.byKey(const Key('storefront_tier_plus'));
    expect(find.descendant(of: current, matching: find.textContaining('•')), findsNothing);
    expect(find.byKey(const Key('storefront_renewal_plus')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('compact and current cards render no bullets', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture('free_settings')));
    final free = find.byKey(const Key('storefront_tier_basic'));
    expect(find.descendant(of: free, matching: find.text(r'$0')), findsOneWidget);
    expect(find.descendant(of: free, matching: find.textContaining('•')), findsNothing);
    expect(find.descendant(of: free, matching: find.byType(OmiButton)), findsNothing);

    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()));
    final plus = find.byKey(const Key('storefront_tier_plus'));
    expect(find.descendant(of: plus, matching: find.text('Your plan')), findsOneWidget);
    expect(find.descendant(of: plus, matching: find.text(r'$19.99/month')), findsOneWidget);
    expect(find.descendant(of: plus, matching: find.textContaining('•')), findsNothing);
    expect(find.byKey(const Key('storefront_buy_plus')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
