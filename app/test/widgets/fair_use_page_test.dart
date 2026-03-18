import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

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
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (pct / 100).clamp(0.0, 1.0),
              backgroundColor: const Color(0xFF2C2C2E),
              valueColor: AlwaysStoppedAnimation<Color>(barColor),
              minHeight: 6,
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
// card tree (stage card, usage section, message card, info section) is
// testable.
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

    Color stageColor;
    IconData stageIcon;
    String stageLabel;

    switch (stage) {
      case 'warning':
        stageColor = const Color(0xFFFBBF24);
        stageIcon = FontAwesomeIcons.triangleExclamation;
        stageLabel = l10n.fairUseStageWarning;
        break;
      case 'throttle':
        stageColor = const Color(0xFFF97316);
        stageIcon = FontAwesomeIcons.gaugeHigh;
        stageLabel = l10n.fairUseStageThrottle;
        break;
      case 'restrict':
        stageColor = const Color(0xFFEF4444);
        stageIcon = FontAwesomeIcons.ban;
        stageLabel = l10n.fairUseStageRestrict;
        break;
      default:
        stageColor = const Color(0xFF34D399);
        stageIcon = FontAwesomeIcons.solidCircleCheck;
        stageLabel = l10n.fairUseStageNormal;
    }

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
            // ---------- stage card ----------
            Container(
              key: const Key('stage_card'),
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: stageColor.withValues(alpha: 0.3)),
              ),
              child: Column(
                children: [
                  FaIcon(stageIcon, color: stageColor, size: 32),
                  const SizedBox(height: 12),
                  Text(
                    stageLabel,
                    style: TextStyle(color: stageColor, fontSize: 18, fontWeight: FontWeight.w600),
                  ),
                  if (caseRef.isNotEmpty) ...[
                    const SizedBox(height: 8),
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
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration:
                            BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(8)),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              caseRef,
                              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontFamily: 'monospace'),
                            ),
                            const SizedBox(width: 6),
                            const Icon(Icons.copy, size: 14, color: Color(0xFF8E8E93)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),
            // ---------- usage section ----------
            Container(
              key: const Key('usage_section'),
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.fairUseSpeechUsage,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 16),
                  _bar(l10n.fairUseToday, speechToday, (limits['daily_hours'] as num?)?.toDouble() ?? 2.0,
                      (usagePct['daily'] as num?)?.toDouble() ?? 0),
                  const SizedBox(height: 12),
                  _bar(l10n.fairUse3Day, speech3day, (limits['three_day_hours'] as num?)?.toDouble() ?? 8.0,
                      (usagePct['three_day'] as num?)?.toDouble() ?? 0),
                  const SizedBox(height: 12),
                  _bar(l10n.fairUseWeekly, speechWeekly, (limits['weekly_hours'] as num?)?.toDouble() ?? 10.0,
                      (usagePct['weekly'] as num?)?.toDouble() ?? 0),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // ---------- message card ----------
            if (message.isNotEmpty)
              Container(
                key: const Key('message_card'),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const FaIcon(FontAwesomeIcons.circleInfo, color: Color(0xFF8E8E93), size: 16),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(message, style: const TextStyle(color: Color(0xFFCCCCCC), fontSize: 14, height: 1.4)),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 16),
            // ---------- info section ----------
            Container(
              key: const Key('info_section'),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(16)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.fairUseAboutTitle,
                      style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Text(l10n.fairUseAboutBody,
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, height: 1.5)),
                ],
              ),
            ),
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
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: (pct / 100).clamp(0.0, 1.0),
            backgroundColor: const Color(0xFF2C2C2E),
            valueColor: AlwaysStoppedAnimation<Color>(barColor),
            minHeight: 6,
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
              const FaIcon(FontAwesomeIcons.circleExclamation, color: Colors.red, size: 40),
              const SizedBox(height: 16),
              Text(l10n.fairUseLoadError,
                  style: const TextStyle(color: Colors.white, fontSize: 16), textAlign: TextAlign.center),
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
  // 1. Loading state — uses a harness that renders the exact loading UI
  //    from FairUsePage (CircularProgressIndicator on black background).
  //    We cannot use the real FairUsePage here because initState() fires
  //    getFairUseStatus() which resolves immediately in the test env.
  // -----------------------------------------------------------------------
  group('Loading state', () {
    // Note: CircularProgressIndicator has an infinite animation, so we use
    // pump() (single frame) rather than pumpAndSettle() which would time out.

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
  // 2. Error state — uses harness to render the identical error UI.
  // -----------------------------------------------------------------------
  group('Error state', () {
    testWidgets('displays error icon and message', (tester) async {
      await tester.pumpWidget(buildTestApp(const FairUseErrorHarness()));
      await tester.pumpAndSettle();

      expect(find.byIcon(FontAwesomeIcons.circleExclamation), findsOneWidget);
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
  // 3. Success render — stage cards for each stage value.
  // -----------------------------------------------------------------------
  group('Success render - stage cards', () {
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

    testWidgets('stage=none shows Normal label and check icon', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'none'))));
      await tester.pumpAndSettle();

      expect(find.text('Normal'), findsOneWidget);
      expect(find.byIcon(FontAwesomeIcons.solidCircleCheck), findsOneWidget);
    });

    testWidgets('stage=warning shows Warning label and triangle icon', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'warning'))));
      await tester.pumpAndSettle();

      expect(find.text('Warning'), findsOneWidget);
      expect(find.byIcon(FontAwesomeIcons.triangleExclamation), findsOneWidget);
    });

    testWidgets('stage=throttle shows Throttled label and gauge icon', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'throttle'))));
      await tester.pumpAndSettle();

      expect(find.text('Throttled'), findsOneWidget);
      expect(find.byIcon(FontAwesomeIcons.gaugeHigh), findsOneWidget);
    });

    testWidgets('stage=restrict shows Restricted label and ban icon', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(stage: 'restrict'))));
      await tester.pumpAndSettle();

      expect(find.text('Restricted'), findsOneWidget);
      expect(find.byIcon(FontAwesomeIcons.ban), findsOneWidget);
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

    testWidgets('renders About Fair Use section', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus())));
      await tester.pumpAndSettle();

      expect(find.text('About Fair Use'), findsOneWidget);
    });

    testWidgets('message card shown when message is non-empty', (tester) async {
      await tester.pumpWidget(
        buildTestApp(FairUseSuccessHarness(status: makeStatus(message: 'Your usage is elevated'))),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your usage is elevated'), findsOneWidget);
      expect(find.byIcon(FontAwesomeIcons.circleInfo), findsOneWidget);
    });

    testWidgets('message card hidden when message is empty', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(message: ''))));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('message_card')), findsNothing);
    });

    testWidgets('case_ref shown when non-empty', (tester) async {
      await tester.pumpWidget(
        buildTestApp(FairUseSuccessHarness(status: makeStatus(caseRef: 'CASE-1234'))),
      );
      await tester.pumpAndSettle();

      expect(find.text('CASE-1234'), findsOneWidget);
      expect(find.byIcon(Icons.copy), findsOneWidget);
    });

    testWidgets('case_ref hidden when empty', (tester) async {
      await tester.pumpWidget(buildTestApp(FairUseSuccessHarness(status: makeStatus(caseRef: ''))));
      await tester.pumpAndSettle();

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
