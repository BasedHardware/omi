import 'package:flutter/material.dart';

import '../art.dart';
import '../content.dart';
import '../theme.dart';
import '../widgets.dart';

enum DfPlan { yearly, monthly }

/// 14 — Soft paywall at the end of onboarding.
///
/// Soft: "Continue with Free" is always visible. A paired Omi works on Free
/// (300 cloud minutes a month, then on-device), so nobody is blocked.
/// Only [trial] changes between the arms of the trial-length test.
class SoftPaywallScreen extends StatefulWidget {
  const SoftPaywallScreen({
    super.key,
    required this.name,
    required this.trial,
    required this.onStartTrial,
    required this.onContinueFree,
  });

  final String name;
  final TrialLength trial;
  final ValueChanged<DfPlan> onStartTrial;
  final VoidCallback onContinueFree;

  @override
  State<SoftPaywallScreen> createState() => _SoftPaywallScreenState();
}

class _SoftPaywallScreenState extends State<SoftPaywallScreen> {
  DfPlan _plan = DfPlan.yearly;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final trial = widget.trial;
    final top = MediaQuery.paddingOf(context).top;
    return DfPage(
      spacing: 10,
      header: SizedBox(
        height: 140 + top,
        child: Stack(
          children: <Widget>[
            const Positioned.fill(child: DfPaywallArt()),
            Positioned(
              left: 8,
              right: 20,
              top: top + 8,
              child: Row(
                children: <Widget>[
                  IconButton(
                    tooltip: 'Close',
                    onPressed: widget.onContinueFree,
                    icon: Icon(Icons.close, color: t.text),
                  ),
                  const Spacer(),
                  Text('Restore', style: t.label(size: 14)),
                ],
              ),
            ),
          ],
        ),
      ),
      children: <Widget>[
        DfEyebrow('For ${widget.name}'),
        DfHeadline(trial.headline, size: 28),
        const DfCompareTable(
          columns: <String>['Free', 'Unlimited'],
          rows: <List<String>>[
            <String>['Cloud minutes', '300 / mo', 'Unlimited'],
            <String>['Real-time + speakers', '✕', '✓'],
            <String>['Ask Omi', '30 / mo', '1,000 / mo'],
          ],
        ),
        DfTrialTimeline(trial: trial),
        DfPlanOption(
          title: 'Yearly',
          badge: 'Best value',
          subtitle: '${trial.label} free, then ${DfPricing.yearly}',
          price: DfPricing.yearlyPerMonth,
          per: 'billed yearly',
          selected: _plan == DfPlan.yearly,
          onTap: () => setState(() => _plan = DfPlan.yearly),
        ),
        DfPlanOption(
          title: 'Monthly',
          subtitle: '${trial.label} free',
          price: DfPricing.monthly,
          per: 'billed monthly',
          selected: _plan == DfPlan.monthly,
          onTap: () => setState(() => _plan = DfPlan.monthly),
        ),
        const Spacer(),
        DfButton(trial.cta, onPressed: () => widget.onStartTrial(_plan)),
        DfCaption('\$0 today · Cancel anytime before day ${trial.days}'),
        DfButton('Continue with Free', onPressed: widget.onContinueFree, kind: DfButtonKind.text),
      ],
    );
  }
}

/// 15 — Trial started. Restates the reminder promise, then one first action.
class TrialStartedScreen extends StatelessWidget {
  const TrialStartedScreen({super.key, required this.name, required this.trial, required this.onStart});

  final String name;
  final TrialLength trial;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final notice = trial.daysOfNotice == 1 ? 'one day' : '${trial.daysOfNotice} days';
    return DfPage(
      children: <Widget>[
        const Spacer(),
        Container(
          width: 72,
          height: 72,
          alignment: Alignment.center,
          decoration: BoxDecoration(shape: BoxShape.circle, gradient: t.accentGradient),
          child: Icon(Icons.notifications_none, size: 32, color: t.onAccent),
        ),
        DfHeadline("You're all set, $name.", size: 34),
        DfBody(
          "Unlimited is on. We'll remind you on day ${trial.reminderDay}, $notice before ${trial.endingNoun} ends.",
        ),
        DfCard(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const DfEyebrow('Try this first'),
              const SizedBox(height: 6),
              Text(
                'Keep your Omi on through your next meeting, then ask: "What did I promise to follow up on?"',
                style: t.label(),
              ),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Start Using Omi', onPressed: onStart),
      ],
    );
  }
}
