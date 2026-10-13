import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
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
  if (evidence.isNotEmpty) {
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
  testWidgets('monthly default, explicit annual savings and exact checkout id', (tester) async {
    String? selectedId;
    await pumpSheet(tester,
        data: PlanStorefront.fromJson(fixture()), select: (_, price) async => selectedId = price.id);
    expect(find.textContaining('Save 16.7%'), findsNothing);
    expect(find.byKey(const Key('storefront_buy_plus')), findsNothing); // current monthly price
    await capture(tester, '001-mobile-ios-storefront-monthly.png');
    await tester.tap(find.byKey(const Key('storefront_year')));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_buy_plus')), 200,
        scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('Save 16.7%'), findsWidgets);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('storefront_tier_plus'))), alignment: 0);
    await capture(tester, '002-mobile-ios-storefront-annual.png');
    await tester.scrollUntilVisible(find.byKey(const Key('storefront_buy_operator')), 250,
        scrollable: find.byType(Scrollable).first);
    expect(find.text('Recommended'), findsOneWidget);
    await Scrollable.ensureVisible(tester.element(find.byKey(const Key('storefront_tier_operator'))), alignment: 0);
    await capture(tester, '003-mobile-ios-storefront-pro.png');
    await tester.tap(find.byKey(const Key('storefront_buy_operator')));
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
      expect(find.byType(OmiCloseButton), findsOneWidget);
      final index = {'loading': '005', 'empty': '006', 'error': '007'}[state];
      await capture(tester, '$index-mobile-ios-storefront-$state.png');
      if (state == 'error') {
        await tester.tap(find.text('Try Again'));
        await tester.pump();
        expect(retried, isTrue);
      }
      await tester.scrollUntilVisible(find.byKey(const Key('storefront_manage')), 150,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.byKey(const Key('storefront_manage')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('storefront_restore')));
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
      'name': 'Unlimited',
      'price_id': 'fixture_legacy',
      'legacy': true,
      'message': 'Your legacy plan stays unchanged unless you choose a different plan.'
    };
    await pumpSheet(tester, data: PlanStorefront.fromJson(json));
    expect(find.text('Current · Unlimited'), findsOneWidget);
    expect(find.textContaining('legacy plan stays unchanged'), findsOneWidget);
    await capture(tester, '008-mobile-ios-storefront-legacy.png');
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
    await tester.tap(find.text('Manage Plan'));
    await tester.pumpAndSettle();
    expect(opened, isTrue);
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
          size: const Size(430, 1800),
          select: (_, price) async => selectedId = price.id);
      final card = find.byKey(Key('storefront_tier_${entry.value}'));
      expect(find.descendant(of: card, matching: find.text('Recommended')), findsOneWidget);
      expect(selectedId, isNull);
      final index =
          {'free_budget': '014', 'free_pro_gate': '015', 'plus_budget': '016', 'free_mcp_cap': '017'}[entry.key];
      await Scrollable.ensureVisible(tester.element(card), alignment: 0);
      await capture(tester, '$index-mobile-ios-${entry.key.replaceAll('_', '-')}.png');
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('hidden storefront never renders offers or actions', (tester) async {
    await pumpSheet(tester, data: PlanStorefront.fromJson(fixture()..['show_subscription_ui'] = false));
    expect(find.byKey(const Key('storefront_tier_operator')), findsNothing);
    expect(find.byKey(const Key('storefront_manage')), findsNothing);
  });
}
