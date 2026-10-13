import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/settings/widgets/plans/storefront_plans_content.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/ui/ui.dart';

Map<String, dynamic> fixture() => jsonDecode(File('test/fixtures/plan_storefront.json').readAsStringSync());
const evidence = String.fromEnvironment('OMI_STOREFRONT_UI_EVIDENCE_DIR');
const boundaryKey = Key('storefront_evidence');

Future<void> capture(WidgetTester tester, String name) async {
  if (evidence.isEmpty) return;
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
  // TextButton's explicit style can have no font family. Flutter's test engine
  // then uses Ahem even after asset fonts load. Normalize that default to the
  // bundled iOS product font for evidence, preserving text, roles and layout.
  InlineSpan productFont(InlineSpan span) {
    if (span is! TextSpan) return span;
    return TextSpan(
      text: span.text,
      style: (span.style ?? const TextStyle()).copyWith(fontFamily: span.style?.fontFamily ?? 'SF Pro Display'),
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

Future<void> pumpSheet(WidgetTester tester,
    {PlanStorefront? data,
    bool loading = false,
    bool failed = false,
    bool dark = true,
    Size size = const Size(390, 844),
    double scale = 1,
    Widget? content,
    String title = 'Plans & Billing',
    Future<void> Function(StorefrontTier, StorefrontPrice)? select,
    VoidCallback? retry,
    VoidCallback? manage,
    VoidCallback? restore}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final previousPalette = OmiColors.active;
  addTearDown(() => OmiColors.active = previousPalette);
  OmiColors.active = dark ? OmiPalette.dark : OmiPalette.light;
  {
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
  }
  // Recreate the capture boundary between states so retained header layers are
  // painted into every standalone screenshot, including empty/error states.
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pumpWidget(RepaintBoundary(
      key: boundaryKey,
      child: MaterialApp(
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
        home: Scaffold(
            body: Align(
                alignment: Alignment.bottomCenter,
                child: OmiSheetScaffold(
                  title: title,
                  padding: EdgeInsets.zero,
                  child: content ??
                      StorefrontPlansContent(
                          storefront: data,
                          loading: loading,
                          failed: failed,
                          onRetry: () async => retry?.call(),
                          onManage: () async => manage?.call(),
                          onRestore: () async => restore?.call(),
                          onSelect: select ?? (_, __) async {}),
                ))),
      )));
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

  testWidgets('monthly default, explicit annual savings and exact checkout id', (tester) async {
    String? selectedId;
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture()), select: (_, price) async => selectedId = price.id);
    expect(find.textContaining('Save 16.7%'), findsNothing);
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing); // current monthly price
    await capture(tester, '001-mobile-ios-storefront-monthly.png');
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_other_plans')), 200,
        scrollable: find.byType(Scrollable).first);
    await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('storefront_other_plans')).hitTestable());
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_buy_plus')), 200,
        scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('Save 16.7%'), findsWidgets);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('storefront_tier_plus'))), alignment: 0);
    await capture(tester, '002-mobile-ios-storefront-annual.png');
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_buy_operator')), -250,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Recommended'), findsOneWidget);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('storefront_tier_operator'))), alignment: 0);
    await capture(tester, '003-mobile-ios-storefront-pro.png');
    await tester.ensureVisible(find.byKey(const Key('storefront_buy_operator')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('storefront_buy_operator')).hitTestable());
    await tester.pumpAndSettle();
    expect(selectedId, 'fixture_operator_year');
    expect(find.byType(OmiCloseButton), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_tier_architect')), 250,
        scrollable: find.byType(Scrollable).first);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('storefront_tier_architect'))), alignment: 0);
    await capture(tester, '004-mobile-ios-storefront-architect.png');
  });

  testWidgets('loading, empty and error keep close, restore and manage reachable', (tester) async {
    for (final state in ['loading', 'empty', 'error']) {
      var retried = false;
      var managed = false;
      var restored = false;
      await pumpSheet(tester,
          data: state == 'empty' ? PlanStorefront.fromJson(fixture()..['tiers'] = []) : null,
          loading: state == 'loading',
          failed: state == 'error',
          retry: () => retried = true,
          manage: () => managed = true,
          restore: () => restored = true);
      expect(find.byType(OmiCloseButton).hitTestable(), findsOneWidget);
      final index = {'loading': '005', 'empty': '006', 'error': '007'}[state];
      await capture(tester, '$index-mobile-ios-storefront-$state.png');
      if (state == 'error') {
        await tester.ensureVisible(find.text('Try Again'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Try Again').hitTestable());
        await tester.pump();
        expect(retried, isTrue);
      }
      await tester.scrollUntilVisible(find.byKey(const Key('storefront_manage')), 150,
          scrollable: find.byType(Scrollable).first);
      await tester.ensureVisible(find.byKey(const Key('storefront_manage')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('storefront_manage')).hitTestable());
      await tester.pump();
      await tester.ensureVisible(find.byKey(const Key('storefront_restore')));
      await tester.pump(); // Loading state intentionally keeps its spinner animating.
      await tester.tap(find.byKey(const Key('storefront_restore')).hitTestable());
      await tester.pump();
      expect(managed, isTrue);
      expect(restored, isTrue);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('legacy current plan stays distinct from the new-buyer ladder', (tester) async {
    final json = fixture();
    json['current'] = {
      'id': 'unlimited_v2',
      'comparison_tier_id': 'plus',
      'name': 'Unlimited',
      'price_id': 'fixture_legacy',
      'legacy': true,
      'message': 'Your legacy plan stays unchanged unless you choose a different plan.'
    };
    await pumpSheet(tester, data: PlanStorefront.fromJson(json));
    expect(find.text('Current · Unlimited · Legacy plan'), findsOneWidget);
    expect(find.textContaining('legacy plan stays unchanged'), findsNothing);
    await capture(tester, '008-mobile-ios-storefront-legacy.png');
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_other_plans')), 200,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Other plans · Free, Plus'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('small light screen and large text wrap without overflow', (tester) async {
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture()), dark: false, size: const Size(320, 568), scale: 1.6);
    expect(find.byType(OmiCloseButton), findsOneWidget);
    await capture(tester, '009-mobile-ios-storefront-small-light.png');
    await tester.drag(find.byKey(const Key('storefront_scroll')), const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('contextual headers explain the feature or daily cap', (tester) async {
    final contexts = [
      ('010', 'proactive-gate', 'Follow through with Pro', 'Let Omi follow up on the commitments you make.'),
      (
        '011',
        'screen-gate',
        'Connect your screen with your memory',
        'Use Pro to connect what you see with what you remember.'
      ),
      (
        '012',
        'mcp-cap',
        'Your daily developer limit is reached',
        'Compare plans for more daily MCP requests; your limit resets tomorrow.'
      ),
    ];
    for (final (index, slug, title, message) in contexts) {
      final json = fixture();
      json['usage_context'].remove('meter');
      json['usage_context'].remove('budget_percent');
      json['usage_context']['title'] = title;
      json['usage_context']['message'] = message;
      await pumpSheet(tester, data: PlanStorefront.fromJson(json));
      expect(find.text(title), findsOneWidget);
      expect(find.text(message), findsOneWidget);
      await capture(tester, '$index-mobile-ios-storefront-$slug.png');
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('80% banner is nonblocking and excludes legacy and 100% snapshots', (tester) async {
    var opened = false;
    final data = PlanStorefront.fromJson(fixture());
    await pumpSheet(tester,
        title: 'Usage',
        size: const Size(390, 350),
        content: BudgetUpsellCard(data: data, onOpen: () async => opened = true));
    expect(find.byKey(const Key('budget_80_percent_banner')), findsOneWidget);
    await capture(tester, '013-mobile-ios-budget-banner.png');
    await tester.tap(find.byKey(const Key('budget_nudge_compare')));
    await tester.pumpAndSettle();
    expect(opened, isTrue);
    expect(tester.getSize(find.byKey(const Key('budget_80_percent_banner'))).height, lessThan(180));
    await tester.tap(find.byKey(const Key('budget_nudge_dismiss')));
    await tester.pump();
    expect(find.byKey(const Key('budget_80_percent_banner')), findsNothing);
    for (final percent in [79, 100, 120]) {
      final json = fixture();
      json['usage_context']['budget_percent'] = percent;
      await pumpSheet(tester, content: BudgetUpsellCard(data: PlanStorefront.fromJson(json), onOpen: () async {}));
      expect(find.byKey(const Key('budget_80_percent_banner')), findsNothing);
    }
    final json = fixture();
    json['current']['legacy'] = true;
    await pumpSheet(tester, content: BudgetUpsellCard(data: PlanStorefront.fromJson(json), onOpen: () async {}));
    expect(find.byKey(const Key('budget_80_percent_banner')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final entry in {
    'free_budget': 'plus',
    'free_pro_gate': 'operator',
    'plus_budget': 'operator',
    'free_mcp_cap': 'plus'
  }.entries) {
    testWidgets('renders backend recommendation for ${entry.key} without selecting a tier', (tester) async {
      String? selectedId;
      final json = jsonDecode(File('test/fixtures/plan_storefront_${entry.key}.json').readAsStringSync())
          as Map<String, dynamic>;
      await pumpSheet(tester,
          data: PlanStorefront.fromJson(json),
          size: const Size(320, 568),
          select: (_, price) async => selectedId = price.id);
      final card = find.byKey(Key('storefront_tier_${entry.value}'));
      expect(find.descendant(of: card, matching: find.text('Recommended')), findsOneWidget);
      expect(selectedId, isNull);
      final index =
          {'free_budget': '014', 'free_pro_gate': '015', 'plus_budget': '016', 'free_mcp_cap': '017'}[entry.key];
      final buy = find.byKey(Key('storefront_buy_${entry.value}'));
      expect(buy.hitTestable(), findsOneWidget);
      expect(tester.getBottomRight(buy).dy, lessThanOrEqualTo(568));
      expect(tester.getBottomRight(find.byKey(Key('storefront_price_${entry.value}'))).dy, lessThan(568));
      await capture(tester, '$index-mobile-ios-${entry.key.replaceAll('_', '-')}.png');
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('recommendation leads and current/lower plans remain expandable in backend order', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()));
    expect(find.byKey(const Key('storefront_tier_basic')), findsNothing);
    expect(find.byKey(const Key('storefront_tier_plus')), findsNothing);
    expect(find.text(r'Current · Plus · $19.99/mo · Renews Nov 1'), findsOneWidget);
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_other_plans')), 200,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Other plans · Free, Plus'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
    await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('storefront_other_plans')).hitTestable());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('storefront_tier_basic')), findsOneWidget);
    expect(find.byKey(const Key('storefront_tier_plus')), findsOneWidget);
    expect(tester.getTopLeft(find.byKey(const Key('storefront_tier_basic'))).dy,
        lessThan(tester.getTopLeft(find.byKey(const Key('storefront_tier_plus'))).dy));
  });

  testWidgets('missing billing fields are omitted and a new period restores a dismissed nudge', (tester) async {
    final json = fixture();
    json['current'].remove('formatted_price');
    json['current'].remove('renewal_label');
    await pumpSheet(tester, data: PlanStorefront.fromJson(json));
    expect(find.text('Current · Plus'), findsOneWidget);
    final data = PlanStorefront.fromJson(json);
    await pumpSheet(tester, content: BudgetUpsellCard(data: data, onOpen: () async {}));
    await tester.tap(find.byKey(const Key('budget_nudge_dismiss')));
    await tester.pump();
    expect(find.byKey(const Key('budget_80_percent_banner')), findsNothing);
    json['usage_context']['period_id'] = '2026-11';
    await pumpSheet(tester, content: BudgetUpsellCard(data: PlanStorefront.fromJson(json), onOpen: () async {}));
    expect(find.byKey(const Key('budget_80_percent_banner')), findsOneWidget);
  });

  testWidgets('small light phone opens with the recommended price and action in the viewport', (tester) async {
    final json =
        jsonDecode(File('test/fixtures/plan_storefront_free_budget.json').readAsStringSync()) as Map<String, dynamic>;
    await pumpSheet(tester, data: PlanStorefront.fromJson(json), dark: false, size: const Size(320, 568));
    final action = find.byKey(const Key('storefront_buy_plus'));
    expect(action.hitTestable(), findsOneWidget);
    expect(tester.getBottomRight(action).dy, lessThanOrEqualTo(568));
    expect(tester.getSize(action).height, greaterThanOrEqualTo(44));
    expect(find.byType(OmiCloseButton).hitTestable(), findsOneWidget);
    await capture(tester, '018-mobile-ios-small-light-budget-fold.png');
  });

  testWidgets('expanded other plans retain current billing controls', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()));
    await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
    await tester.ensureVisible(find.byKey(const Key('storefront_other_plans')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('storefront_other_plans')).hitTestable());
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('storefront_tier_basic')));
    await capture(tester, '019-mobile-ios-storefront-other-plans.png');
    expect(find.byKey(const Key('storefront_tier_plus')), findsOneWidget);
  });

  for (final dark in [true, false]) {
    testWidgets('real draggable sheet keeps Pro price and CTA above the small-phone fold (dark=$dark)', (tester) async {
      await pumpSheet(tester, dark: dark, size: const Size(320, 568), content: const SizedBox.shrink());
      final data = PlanStorefront.fromJson(fixture());
      final closed = showOmiSheet<void>(
        context: tester.element(find.byType(Scaffold)),
        title: 'Plans & Billing',
        padding: EdgeInsets.zero,
        builder: (_) => StorefrontPlansContent(
          storefront: data,
          onRetry: () async {},
          onSelect: (_, __) async {},
          onManage: () async {},
          onRestore: () async {},
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

  testWidgets('hidden storefront never renders offers or actions', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()..['show_subscription_ui'] = false));
    expect(find.byKey(const Key('storefront_tier_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_manage')), findsNothing);
  });
}
