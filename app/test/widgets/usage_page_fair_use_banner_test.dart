import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/fair_use_page.dart';

/// Wraps [child] in a MaterialApp with l10n delegates so context.l10n works.
Widget buildTestApp(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: const [Locale('en')],
    home: child,
  );
}

// ---------------------------------------------------------------------------
// Harness replicating the _buildFairUseBanner logic from UsagePage.
// This lets us test banner visibility/styling without the full UsagePage
// widget tree and its HTTP dependencies.
// ---------------------------------------------------------------------------

class FairUseBannerHarness extends StatelessWidget {
  const FairUseBannerHarness({super.key, required this.fairUseStatus});
  final Map<String, dynamic>? fairUseStatus;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      body: Column(
        children: [
          _buildFairUseBanner(context, l10n),
        ],
      ),
    );
  }

  Widget _buildFairUseBanner(BuildContext context, AppLocalizations l10n) {
    if (fairUseStatus == null) return const SizedBox.shrink();
    final stage = fairUseStatus!['stage'] as String? ?? 'none';
    if (stage == 'none') return const SizedBox.shrink();

    Color dotColor;
    String stageLabel;
    switch (stage) {
      case 'warning':
        dotColor = const Color(0xFFFBBF24);
        stageLabel = l10n.fairUseStageWarning;
        break;
      case 'throttle':
        dotColor = const Color(0xFFF97316);
        stageLabel = l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        dotColor = const Color(0xFFEF4444);
        stageLabel = l10n.fairUseStageRestrict;
        break;
      default:
        return const SizedBox.shrink();
    }

    return GestureDetector(
      key: const Key('fair_use_banner_tap'),
      onTap: () {
        Navigator.of(context).push(MaterialPageRoute(builder: (context) => const FairUsePage()));
      },
      child: Container(
        margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: dotColor.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Container(
              key: const Key('fair_use_dot'),
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
            ),
            const SizedBox(width: 10),
            Text(
              l10n.fairUseBannerStatus(stageLabel),
              style: TextStyle(color: dotColor, fontSize: 13, fontWeight: FontWeight.w500),
            ),
            const Spacer(),
            Icon(Icons.chevron_right, color: dotColor, size: 18),
          ],
        ),
      ),
    );
  }
}

void main() {
  group('Fair Use banner visibility', () {
    testWidgets('hidden when status is null', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: null)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsNothing);
    });

    testWidgets('hidden when stage is none', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'none'})));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsNothing);
    });

    testWidgets('hidden for unknown stage', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'bogus'})));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsNothing);
    });

    testWidgets('visible for warning stage', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'warning'})));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsOneWidget);
      expect(find.textContaining('Warning'), findsOneWidget);
    });

    testWidgets('visible for throttle stage', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'throttle'})));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsOneWidget);
      expect(find.textContaining('Throttled'), findsOneWidget);
    });

    testWidgets('visible for restrict stage', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'restrict'})));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('fair_use_banner_tap')), findsOneWidget);
      expect(find.textContaining('Restricted'), findsOneWidget);
    });
  });

  group('Fair Use banner styling', () {
    testWidgets('warning uses amber dot color', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'warning'})));
      await tester.pumpAndSettle();

      final dot = tester.widget<Container>(find.byKey(const Key('fair_use_dot')));
      final decoration = dot.decoration as BoxDecoration;
      expect(decoration.color, const Color(0xFFFBBF24));
    });

    testWidgets('throttle uses orange dot color', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'throttle'})));
      await tester.pumpAndSettle();

      final dot = tester.widget<Container>(find.byKey(const Key('fair_use_dot')));
      final decoration = dot.decoration as BoxDecoration;
      expect(decoration.color, const Color(0xFFF97316));
    });

    testWidgets('restrict uses red dot color', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'restrict'})));
      await tester.pumpAndSettle();

      final dot = tester.widget<Container>(find.byKey(const Key('fair_use_dot')));
      final decoration = dot.decoration as BoxDecoration;
      expect(decoration.color, const Color(0xFFEF4444));
    });

    testWidgets('banner has chevron icon', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'warning'})));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.chevron_right), findsOneWidget);
    });
  });

  group('Fair Use banner tap target', () {
    testWidgets('tapping banner navigates to FairUsePage', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'stage': 'restrict'})));
      await tester.pumpAndSettle();

      final gesture = find.byKey(const Key('fair_use_banner_tap'));
      expect(gesture, findsOneWidget);

      // Tap the banner
      await tester.tap(gesture);
      await tester.pumpAndSettle();

      // Verify FairUsePage was pushed onto the navigator
      expect(find.byType(FairUsePage), findsOneWidget);
    });
  });

  group('Fair Use banner missing stage key', () {
    testWidgets('hidden when status map has no stage key', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseBannerHarness(fairUseStatus: {'other': 'data'})));
      await tester.pumpAndSettle();

      // Default stage is 'none', so banner should be hidden
      expect(find.byKey(const Key('fair_use_banner_tap')), findsNothing);
    });
  });
}
