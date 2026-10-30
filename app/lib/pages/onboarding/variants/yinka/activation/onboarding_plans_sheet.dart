import 'package:flutter/material.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';

/// The plans sheet shown at the end of onboarding (until the Superwall paywall replaces it).
class OnboardingPlansSheet extends StatefulWidget {
  const OnboardingPlansSheet({super.key});

  @override
  State<OnboardingPlansSheet> createState() => _OnboardingPlansSheetState();
}

class _OnboardingPlansSheetState extends State<OnboardingPlansSheet> with TickerProviderStateMixin {
  late final AnimationController _wave = AnimationController(duration: const Duration(milliseconds: 18000), vsync: this)
    ..repeat();
  late final AnimationController _arrow = AnimationController(duration: const Duration(milliseconds: 800), vsync: this)
    ..repeat(reverse: true);
  late final Animation<double> _arrowOffset =
      Tween<double>(begin: 0, end: 3).animate(CurvedAnimation(parent: _arrow, curve: Curves.easeInOut));

  @override
  void dispose() {
    _wave.dispose();
    _arrow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _wave,
      notesController: _wave,
      arrowController: _arrow,
      arrowAnimation: _arrowOffset,
      // Not yet a registered paywall source; reported as "unknown" until added to the registry.
      analyticsSource: 'onboarding',
    );
  }
}
