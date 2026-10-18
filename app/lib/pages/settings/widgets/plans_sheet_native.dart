part of 'plans_sheet.dart';

/// Asks the native alert first; when it is not used (null) the existing dialog asks instead. Resolves
/// true only when the reader chose [confirmLabel].
Future<bool> _confirmPlanChange(
  BuildContext context, {
  required String title,
  required String heading,
  required List<String> lines,
  required String confirmLabel,
  required bool destructive,
  required Widget Function(BuildContext dialogContext) dialog,
}) async {
  final native = await showIosNativeModal(context, title: title, alert: true, actions: [
    NativeRow('cancel', context.l10n.cancel, symbol: 'xmark'),
    NativeRow('confirm', confirmLabel, destructive: destructive),
  ], sections: [
    NativeSection('confirmation', [
      NativeRow('message', [heading, for (final line in lines) '• $line'].join('\n'), kind: 'label'),
    ]),
  ]);
  if (native != null) return native.action == 'confirm';
  if (!context.mounted) return false;
  return await showDialog<bool>(context: context, builder: dialog) == true;
}

/// Confirms a switch to the free (on-device) plan, listing what the reader loses.
Future<bool> confirmFreemiumDowngrade(BuildContext context) {
  final l10n = context.l10n;
  return _confirmPlanChange(
    context,
    title: l10n.downgradeToFreemiumTitle,
    heading: l10n.downgradeLimitationsHeading,
    lines: [
      l10n.downgradeLimitBattery,
      l10n.downgradeLimitQuality,
      l10n.downgradeLimitDelay,
      l10n.downgradeLimitSpeakers
    ],
    confirmLabel: l10n.downgradeAnyway,
    destructive: true,
    dialog: (ctx) => OmiAlertDialog(
      title: l10n.downgradeToFreemiumTitle,
      content: Material(
        type: MaterialType.transparency,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.downgradeLimitationsHeading, textAlign: TextAlign.start, style: OmiType.subhead),
            const SizedBox(height: OmiSpacing.xs),
            PlanDialogLine(
              icon: FontAwesomeIcons.carBattery,
              text: l10n.downgradeLimitBattery,
              color: OmiColors.danger,
            ),
            PlanDialogLine(
              icon: FontAwesomeIcons.triangleExclamation,
              text: l10n.downgradeLimitQuality,
              color: OmiColors.danger,
            ),
            PlanDialogLine(icon: FontAwesomeIcons.clock, text: l10n.downgradeLimitDelay, color: OmiColors.danger),
            PlanDialogLine(
              icon: FontAwesomeIcons.userSlash,
              text: l10n.downgradeLimitSpeakers,
              color: OmiColors.danger,
            ),
          ],
        ),
      ),
      actions: [
        OmiDialogAction(label: l10n.cancel, isDefault: true, onPressed: () => Navigator.of(ctx).pop(false)),
        OmiDialogAction(
          label: l10n.downgradeAnyway,
          isDestructive: true,
          onPressed: () => Navigator.of(ctx).pop(true),
        ),
      ],
    ),
  );
}

/// Confirms a same-tier monthly-to-annual switch with its billing information.
Future<bool> confirmAnnualPlanSwitch(BuildContext context) {
  final l10n = context.l10n;
  return _confirmPlanChange(
    context,
    title: l10n.upgradeToAnnualPlan,
    heading: l10n.importantBillingInfo,
    lines: [
      l10n.monthlyPlanContinues,
      l10n.paymentMethodCharged,
      l10n.annualSubscriptionStarts,
      l10n.thirteenMonthsCoverage,
    ],
    confirmLabel: l10n.confirmUpgrade,
    destructive: false,
    dialog: (ctx) => OmiAlertDialog(
      title: l10n.upgradeToAnnualPlan,
      content: Material(
        type: MaterialType.transparency,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              l10n.importantBillingInfo,
              textAlign: TextAlign.start,
              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: OmiSpacing.xxs),
            PlanDialogLine(icon: FontAwesomeIcons.clock, text: l10n.monthlyPlanContinues),
            PlanDialogLine(icon: FontAwesomeIcons.creditCard, text: l10n.paymentMethodCharged),
            PlanDialogLine(icon: FontAwesomeIcons.calendarDay, text: l10n.annualSubscriptionStarts),
            const SizedBox(height: OmiSpacing.xs),
            PlanDialogLine(
              icon: FontAwesomeIcons.circleInfo,
              text: l10n.thirteenMonthsCoverage,
              color: OmiColors.success,
            ),
          ],
        ),
      ),
      actions: [
        OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.of(ctx).pop(false)),
        OmiDialogAction(label: l10n.confirmUpgrade, isDefault: true, onPressed: () => Navigator.of(ctx).pop(true)),
      ],
    ),
  );
}

/// Repeats the hero controllers while the classic plans tree is mounted and stops the ones it started on dispose.
class _ClassicHeroAnimations extends StatefulWidget {
  const _ClassicHeroAnimations({required this.controllers, required this.reversing, required this.child});

  final List<AnimationController> controllers;
  final List<AnimationController> reversing;
  final Widget child;

  @override
  State<_ClassicHeroAnimations> createState() => _ClassicHeroAnimationsState();
}

class _ClassicHeroAnimationsState extends State<_ClassicHeroAnimations> {
  final _started = <AnimationController>{};

  @override
  void initState() {
    super.initState();
    for (final controller in {...widget.controllers, ...widget.reversing}) {
      if (controller.isAnimating) continue;
      _started.add(controller);
      controller.repeat(reverse: widget.reversing.contains(controller));
    }
  }

  @override
  void dispose() {
    for (final controller in _started) {
      controller.stop();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
