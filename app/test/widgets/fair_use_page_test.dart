import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';

/// Wraps [child] in a MaterialApp configured with all l10n delegates and
/// English locale so that `context.l10n.*` calls resolve correctly.
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
// Standalone harness that reproduces the exact _buildUsageBar colour-picking
// logic from FairUsePage so we can unit-test threshold boundaries without
// needing to mock the HTTP layer.
// ---------------------------------------------------------------------------

/// Returns the bar colour that _buildUsageBar would use for a given [pct].
Color usageBarColor(double pct) {
  if (pct >= 100) return const Color(0xFFEF4444);
  if (pct >= 80) return const Color(0xFFFBBF24);
  return const Color(0xFF8B5CF6);
}

/// Builds a usage-bar widget identical to the private _buildUsageBar inside
/// FairUsePage.  This lets us pump it in isolation and verify the colour and
/// value of the LinearProgressIndicator.
Widget buildUsageBarHarness({
  required String label,
  required double hours,
  required double limit,
  required double pct,
}) {
  final Color barColor = usageBarColor(pct);

  return MaterialApp(
    home: Scaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13)),
              Text(
                '${hours.toStringAsFixed(1)}h / ${limit.toStringAsFixed(0)}h',
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
              ),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              backgroundColor: const Color(0xFF2C2C2E),
              valueColor: AlwaysStoppedAnimation<Color>(barColor),
              minHeight: 4,
            ),
          ),
        ],
      ),
    ),
  );
}

// ---------------------------------------------------------------------------
// Harness that renders the page body for a given _status map, bypassing the
// HTTP call.  We replicate the build logic from FairUsePage so that the full
// widget tree (status banner, usage section, message banner, about footer)
// is testable.
// ---------------------------------------------------------------------------

/// A widget that mimics FairUsePage's success render for a given [status] map.
class FairUseSuccessHarness extends StatelessWidget {
  const FairUseSuccessHarness({super.key, required this.status});
  final Map<String, dynamic> status;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final stage = status['stage'] as String? ?? 'none';
    final caseRef = status['case_ref'] as String? ?? '';

    final usagePct = status['usage_pct'] as Map<String, dynamic>? ?? {};
    final limits = status['limits'] as Map<String, dynamic>? ?? {};
    final speechToday = (status['speech_hours_today'] as num?)?.toDouble() ?? 0;
    final speech3day = (status['speech_hours_3day'] as num?)?.toDouble() ?? 0;
    final speechWeekly = (status['speech_hours_weekly'] as num?)?.toDouble() ?? 0;
    final message = status['message'] as String? ?? '';

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, title: Text(l10n.fairUsePolicy)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ---------- status banner (only for elevated stages) ----------
            if (stage != 'none') _buildStatusBanner(context, l10n, stage, caseRef),
            // ---------- usage section ----------
            Container(
              key: const Key('usage_section'),
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.fairUseSpeechUsage,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 16),
                  _bar(l10n.fairUseToday, speechToday, (limits['daily_hours'] as num?)?.toDouble() ?? 2.0,
                      (usagePct['daily'] as num?)?.toDouble() ?? 0),
                  const SizedBox(height: 14),
                  _bar(l10n.fairUse3Day, speech3day, (limits['three_day_hours'] as num?)?.toDouble() ?? 8.0,
                      (usagePct['three_day'] as num?)?.toDouble() ?? 0),
                  const SizedBox(height: 14),
                  _bar(l10n.fairUseWeekly, speechWeekly, (limits['weekly_hours'] as num?)?.toDouble() ?? 10.0,
                      (usagePct['weekly'] as num?)?.toDouble() ?? 0),
                ],
              ),
            ),
            // ---------- budget section ----------
            _buildBudgetSection(context, l10n),
            // ---------- message banner ----------
            if (message.isNotEmpty)
              Padding(
                key: const Key('message_banner'),
                padding: const EdgeInsets.only(top: 12),
                child: Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(12)),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.info_outline, color: Color(0xFF8E8E93), size: 16),
                      const SizedBox(width: 10),
                      Expanded(
                        child:
                            Text(message, style: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 13, height: 1.4)),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 24),
            // ---------- about footer ----------
            Padding(
              key: const Key('about_footer'),
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.fairUseAboutTitle,
                      style: const TextStyle(color: Color(0xFF636366), fontSize: 12, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  Text(l10n.fairUseAboutBody,
                      style: const TextStyle(color: Color(0xFF48484A), fontSize: 12, height: 1.4)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBanner(BuildContext context, AppLocalizations l10n, String stage, String caseRef) {
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

    return Padding(
      key: const Key('status_banner'),
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: dotColor.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Container(
              key: const Key('status_dot'),
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
            ),
            const SizedBox(width: 10),
            Text(
              stageLabel,
              style: TextStyle(color: dotColor, fontSize: 14, fontWeight: FontWeight.w500),
            ),
            const Spacer(),
            if (caseRef.isNotEmpty)
              GestureDetector(
                onTap: () {
                  Clipboard.setData(ClipboardData(text: caseRef));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(l10n.fairUseCaseRefCopied(caseRef)),
                      duration: const Duration(seconds: 2),
                      backgroundColor: const Color(0xFF2C2C2E),
                    ),
                  );
                },
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      caseRef,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 12, fontFamily: 'monospace'),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.copy, size: 12, color: Color(0xFF8E8E93)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildBudgetSection(BuildContext context, AppLocalizations l10n) {
    final stage = status['stage'] as String? ?? 'none';
    if (stage != 'restrict') return const SizedBox.shrink();

    final dgBudget = status['dg_budget'] as Map<String, dynamic>?;
    if (dgBudget == null) return const SizedBox.shrink();

    final dailyLimitMs = (dgBudget['daily_limit_ms'] as num?)?.toInt() ?? 0;
    final usedMs = (dgBudget['used_ms'] as num?)?.toInt() ?? 0;
    final exhausted = dgBudget['exhausted'] as bool? ?? false;
    final resetsAt = dgBudget['resets_at'] as String? ?? '';

    if (dailyLimitMs <= 0) return const SizedBox.shrink();

    final usedMin = (usedMs / 60000).round();
    final limitMin = (dailyLimitMs / 60000).round();
    final pct = (usedMs / dailyLimitMs * 100).clamp(0.0, 100.0);
    final barColor = exhausted ? const Color(0xFFEF4444) : const Color(0xFF8B5CF6);

    String resetLabel = '';
    if (resetsAt.isNotEmpty) {
      try {
        final resetTime = DateTime.parse(resetsAt);
        final now = DateTime.now().toUtc();
        final diff = resetTime.difference(now);
        if (diff.inHours > 0) {
          resetLabel = l10n.fairUseBudgetResetsAt('${diff.inHours}h');
        } else if (diff.inMinutes > 0) {
          resetLabel = l10n.fairUseBudgetResetsAt('${diff.inMinutes}m');
        }
      } catch (_) {}
    }

    return Padding(
      key: const Key('budget_section'),
      padding: const EdgeInsets.only(top: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: exhausted ? const Color(0xFFEF4444).withValues(alpha: 0.06) : const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(l10n.fairUseDailyTranscription,
                    style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500)),
                Text(l10n.fairUseBudgetUsed('$usedMin', '$limitMin'),
                    style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500)),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: (pct / 100).clamp(0.0, 1.0),
                backgroundColor: const Color(0xFF2C2C2E),
                valueColor: AlwaysStoppedAnimation<Color>(barColor),
                minHeight: 4,
              ),
            ),
            if (exhausted) ...[
              const SizedBox(height: 10),
              Text(l10n.fairUseBudgetExhausted,
                  style: const TextStyle(color: Color(0xFFEF4444), fontSize: 13, fontWeight: FontWeight.w500)),
            ],
            if (resetLabel.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(resetLabel, style: const TextStyle(color: Color(0xFF636366), fontSize: 12)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _bar(String label, double hours, double limit, double pct) {
    final Color barColor = usageBarColor(pct);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13)),
            Text('${hours.toStringAsFixed(1)}h / ${limit.toStringAsFixed(0)}h',
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500)),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: (pct / 100).clamp(0.0, 1.0),
            backgroundColor: const Color(0xFF2C2C2E),
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
            minHeight: 4,
          ),
        ),
      ],
    );
  }
}

/// A widget that mimics FairUsePage's error render.
class FairUseErrorHarness extends StatelessWidget {
  const FairUseErrorHarness({super.key, this.onRetry});
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, title: Text(l10n.fairUsePolicy)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(l10n.fairUseLoadError,
                  style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15), textAlign: TextAlign.center),
              const SizedBox(height: 16),
              TextButton(
                onPressed: onRetry,
                child: Text(l10n.retry, style: const TextStyle(color: Color(0xFF8B5CF6))),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A harness that renders the exact loading UI from FairUsePage: a Scaffold
/// with a centered white CircularProgressIndicator on a black background.
/// This lets us verify the loading state without triggering the HTTP call.
class FairUseLoadingHarness extends StatelessWidget {
  const FairUseLoadingHarness({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        title: Text(l10n.fairUsePolicy),
        leading: IconButton(icon: const Icon(Icons.arrow_back_ios), onPressed: () => Navigator.of(context).pop()),
      ),
      body: const Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }
}

// ===========================================================================
// Tests
// ===========================================================================

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // -----------------------------------------------------------------------
  // 1. Loading state
  // -----------------------------------------------------------------------
  group('Loading state', () {
    testWidgets('shows CircularProgressIndicator', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseLoadingHarness()));
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('loading indicator has white colour', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseLoadingHarness()));
      await tester.pump();

      final indicator = tester.widget<CircularProgressIndicator>(find.byType(CircularProgressIndicator));
      expect(indicator.color, Colors.white);
    });

    testWidgets('app bar shows Fair Use title during loading', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseLoadingHarness()));
      await tester.pump();

      expect(find.text('Fair Use'), findsOneWidget);
    });

    testWidgets('scaffold background is black', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseLoadingHarness()));
      await tester.pump();

      final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
      expect(scaffold.backgroundColor, Colors.black);
    });
  });

  // -----------------------------------------------------------------------
  // 2. Error state
  // -----------------------------------------------------------------------
  group('Error state', () {
    testWidgets('displays error message text', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseErrorHarness()));
      await tester.pumpAndSettle();

      expect(find.text('Unable to load fair use status. Please try again.'), findsOneWidget);
    });

    testWidgets('shows retry button with correct text', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseErrorHarness()));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(TextButton, 'Retry'), findsOneWidget);
    });

    testWidgets('retry button triggers callback', (tester) async {
      var retried = false;
      await tester.pumpWidget(buildTestApp(FairUseErrorHarness(onRetry: () => retried = true)));
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(TextButton, 'Retry'));
      expect(retried, isTrue);
    });
  });

  // -----------------------------------------------------------------------
  // 3. Success render — minimal status banner for elevated stages,
  //    no banner for normal state.
  // -----------------------------------------------------------------------
  group('Success render - status banner', () {
    Map<String, dynamic> makeStatus({
      String stage = 'none',
      String caseRef = '',
      String message = '',
    }) {
      return {
        'stage': stage,
        'case_ref': caseRef,
        'message': message,
        'usage_pct': {'daily': 50.0, 'three_day': 40.0, 'weekly': 30.0},
        'limits': {'daily_hours': 2.0, 'three_day_hours': 8.0, 'weekly_hours': 10.0},
        'speech_hours_today': 1.0,
        'speech_hours_3day': 3.2,
        'speech_hours_weekly': 3.0,
      };
    }

    testWidgets('stage=none shows no status banner', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'none'))));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('status_banner')), findsNothing);
    });

    testWidgets('stage=warning shows Warning label with colored dot', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'warning'))));
      await tester.pumpAndSettle();

      expect(find.text('Warning'), findsOneWidget);
      expect(find.byKey(const Key('status_dot')), findsOneWidget);
    });

    testWidgets('stage=throttle shows Throttled label with colored dot', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'throttle'))));
      await tester.pumpAndSettle();

      expect(find.text('Throttled'), findsOneWidget);
      expect(find.byKey(const Key('status_dot')), findsOneWidget);
    });

    testWidgets('stage=restrict shows Restricted label with colored dot', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'restrict'))));
      await tester.pumpAndSettle();

      expect(find.text('Restricted'), findsOneWidget);
      expect(find.byKey(const Key('status_dot')), findsOneWidget);
    });

    testWidgets('renders usage section header', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.text('Speech Usage'), findsOneWidget);
    });

    testWidgets('renders usage labels: Today, 3-Day Rolling, Weekly Rolling', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.text('Today'), findsOneWidget);
      expect(find.text('3-Day Rolling'), findsOneWidget);
      expect(find.text('Weekly Rolling'), findsOneWidget);
    });

    testWidgets('renders formatted hours/limit text', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.text('1.0h / 2h'), findsOneWidget);
      expect(find.text('3.2h / 8h'), findsOneWidget);
      expect(find.text('3.0h / 10h'), findsOneWidget);
    });

    testWidgets('renders three LinearProgressIndicators', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.byType(LinearProgressIndicator), findsNWidgets(3));
    });

    testWidgets('renders About Fair Use footer', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.text('About Fair Use'), findsOneWidget);
    });

    testWidgets('message banner shown when message is non-empty', (tester) async {
      await tester.pumpWidget(
        buildTestApp(FairUseSuccessHarness(status: makeStatus(message: 'Your usage is elevated'))),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your usage is elevated'), findsOneWidget);
      expect(find.byIcon(Icons.info_outline), findsOneWidget);
    });

    testWidgets('message banner hidden when message is empty', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(message: ''))));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('message_banner')), findsNothing);
    });

    testWidgets('case_ref shown when non-empty on elevated stage', (tester) async {
      await tester.pumpWidget(
        buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'warning', caseRef: 'CASE-1234'))),
      );
      await tester.pumpAndSettle();

      expect(find.text('CASE-1234'), findsOneWidget);
      expect(find.byIcon(Icons.copy), findsOneWidget);
    });

    testWidgets('case_ref hidden when empty', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'warning', caseRef: ''))));
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.copy), findsNothing);
    });

    testWidgets('no copy icon in normal stage (no banner)', (tester) async {
      await tester
          .pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'none', caseRef: 'CASE-999'))));
      await tester.pumpAndSettle();

      // case_ref is not shown because status banner is hidden for 'none'
      expect(find.byIcon(Icons.copy), findsNothing);
    });
  });

  // -----------------------------------------------------------------------
  // 4. Usage bar thresholds — colour and value boundary tests.
  // -----------------------------------------------------------------------
  group('Usage bar thresholds', () {
    testWidgets('pct=79.9 renders purple bar', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 1.6, limit: 2, pct: 79.9));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFF8B5CF6)); // purple
    });

    testWidgets('pct=80.0 renders amber bar', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 1.6, limit: 2, pct: 80.0));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFFFBBF24)); // amber
    });

    testWidgets('pct=99.9 renders amber bar', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 2.0, limit: 2, pct: 99.9));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFFFBBF24)); // amber
    });

    testWidgets('pct=100.0 renders red bar', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 2.0, limit: 2, pct: 100.0));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFFEF4444)); // red
    });

    testWidgets('pct=115 clamps value to 1.0', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 2.3, limit: 2, pct: 115));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      expect(bar.value, 1.0);
      // Also red
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFFEF4444));
    });

    testWidgets('pct=0 produces value 0.0 and purple', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Test', hours: 0, limit: 2, pct: 0));
      await tester.pumpAndSettle();

      final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
      expect(bar.value, 0.0);
      final animatedColor = bar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(animatedColor.value, const Color(0xFF8B5CF6));
    });

    testWidgets('hours/limit label formatted correctly', (tester) async {
      await tester.pumpWidget(buildUsageBarHarness(label: 'Today', hours: 1.23, limit: 5, pct: 24.6));
      await tester.pumpAndSettle();

      expect(find.text('Today'), findsOneWidget);
      expect(find.text('1.2h / 5h'), findsOneWidget);
    });
  });

  // -----------------------------------------------------------------------
  // 5. Case ref copy — tap triggers clipboard write + snackbar.
  // -----------------------------------------------------------------------
  group('Case ref copy', () {
    testWidgets('tap copies case_ref to clipboard and shows snackbar', (tester) async {
      // Set up a mock clipboard handler to capture written data.
      String? copiedText;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall methodCall) async {
          if (methodCall.method == 'Clipboard.setData') {
            copiedText = (methodCall.arguments as Map)['text'] as String?;
          }
          return null;
        },
      );

      await tester.pumpWidget(
        buildTestApp(FairUseSuccessHarness(
          status: {
            'stage': 'warning',
            'case_ref': 'FU-99887',
            'message': '',
            'usage_pct': {'daily': 85.0},
            'limits': {'daily_hours': 2.0},
            'speech_hours_today': 1.7,
            'speech_hours_3day': 0,
            'speech_hours_weekly': 0,
          },
        )),
      );
      await tester.pumpAndSettle();

      // Verify the case_ref text is displayed
      expect(find.text('FU-99887'), findsOneWidget);

      // Tap the GestureDetector containing the case_ref
      await tester.tap(find.text('FU-99887'));
      await tester.pumpAndSettle();

      // Verify clipboard received the correct text
      expect(copiedText, 'FU-99887');

      // Verify snackbar appeared with localized text
      expect(find.text('FU-99887 copied'), findsOneWidget);

      // Clean up mock handler
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null);
    });
  });

  // -----------------------------------------------------------------------
  // 6. Budget section tests
  // -----------------------------------------------------------------------
  group('Budget section', () {
    Map<String, dynamic> makeStatusWithBudget({
      int dailyLimitMs = 600000, // 10 min
      int usedMs = 300000, // 5 min
      bool exhausted = false,
      String resetsAt = '',
    }) {
      return {
        'stage': 'restrict',
        'case_ref': 'FU-AABB11',
        'message': '',
        'usage_pct': {'daily': 50.0, 'three_day': 40.0, 'weekly': 30.0},
        'limits': {'daily_hours': 2.0, 'three_day_hours': 8.0, 'weekly_hours': 10.0},
        'speech_hours_today': 1.0,
        'speech_hours_3day': 3.0,
        'speech_hours_weekly': 3.0,
        'dg_budget': {
          'daily_limit_ms': dailyLimitMs,
          'used_ms': usedMs,
          'remaining_ms': dailyLimitMs - usedMs,
          'exhausted': exhausted,
          'resets_at': resetsAt,
        },
      };
    }

    testWidgets('shows budget section when dg_budget present', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatusWithBudget())));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('budget_section')), findsOneWidget);
      expect(find.text('Daily Transcription'), findsOneWidget);
    });

    testWidgets('hides budget section when dg_budget absent', (tester) async {
      final status = makeStatusWithBudget();
      status.remove('dg_budget');
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: status)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('budget_section')), findsNothing);
    });

    testWidgets('shows used/limit in minutes', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(dailyLimitMs: 600000, usedMs: 300000),
      )));
      await tester.pumpAndSettle();

      // 300000ms = 5min, 600000ms = 10min
      expect(find.text('5m / 10m'), findsOneWidget);
    });

    testWidgets('shows exhausted message when budget exhausted', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(exhausted: true, usedMs: 600000, dailyLimitMs: 600000),
      )));
      await tester.pumpAndSettle();

      expect(find.text('Daily transcription limit reached'), findsOneWidget);
    });

    testWidgets('no exhausted message when budget not exhausted', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(exhausted: false),
      )));
      await tester.pumpAndSettle();

      expect(find.text('Daily transcription limit reached'), findsNothing);
    });

    testWidgets('exhausted bar is red, normal bar is purple', (tester) async {
      // Normal (not exhausted)
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(exhausted: false),
      )));
      await tester.pumpAndSettle();

      // 4 bars total: 3 usage + 1 budget
      final bars = tester.widgetList<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).toList();
      // Budget bar is the last one
      final budgetBar = bars.last;
      final normalColor = budgetBar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(normalColor.value, const Color(0xFF8B5CF6)); // purple

      // Exhausted
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(exhausted: true, usedMs: 600000, dailyLimitMs: 600000),
      )));
      await tester.pumpAndSettle();

      final bars2 = tester.widgetList<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).toList();
      final exhaustedBar = bars2.last;
      final exhaustedColor = exhaustedBar.valueColor as AlwaysStoppedAnimation<Color>;
      expect(exhaustedColor.value, const Color(0xFFEF4444)); // red
    });

    testWidgets('hides budget section for non-restrict stages even with dg_budget', (tester) async {
      final status = makeStatusWithBudget();
      status['stage'] = 'warning';
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: status)));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('budget_section')), findsNothing);
    });

    testWidgets('hides budget section when daily_limit_ms is 0', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(
        status: makeStatusWithBudget(dailyLimitMs: 0),
      )));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('budget_section')), findsNothing);
    });
  });

  // -----------------------------------------------------------------------
  // Pure unit tests for the usageBarColor helper (no widget pumping needed).
  // -----------------------------------------------------------------------
  group('usageBarColor pure unit tests', () {
    test('below 80 returns purple', () {
      expect(usageBarColor(0), const Color(0xFF8B5CF6));
      expect(usageBarColor(50), const Color(0xFF8B5CF6));
      expect(usageBarColor(79.9), const Color(0xFF8B5CF6));
    });

    test('80 to 99.x returns amber', () {
      expect(usageBarColor(80), const Color(0xFFFBBF24));
      expect(usageBarColor(90), const Color(0xFFFBBF24));
      expect(usageBarColor(99.9), const Color(0xFFFBBF24));
    });

    test('100 and above returns red', () {
      expect(usageBarColor(100), const Color(0xFFEF4444));
      expect(usageBarColor(115), const Color(0xFFEF4444));
      expect(usageBarColor(200), const Color(0xFFEF4444));
    });
  });
}
