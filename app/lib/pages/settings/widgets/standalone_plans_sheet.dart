import 'package:flutter/material.dart';

import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/ui/ui.dart';

/// [PlansSheet] with its own animation controllers, for callers that open the sheet without
/// hosting the Plan & Usage page's animations.
class StandalonePlansSheet extends StatefulWidget {
  const StandalonePlansSheet({super.key, this.analyticsSource = 'usage_page'});

  final String analyticsSource;

  @override
  State<StandalonePlansSheet> createState() => _StandalonePlansSheetState();
}

class _StandalonePlansSheetState extends State<StandalonePlansSheet> with TickerProviderStateMixin {
  late final AnimationController _waveController =
      AnimationController(duration: const Duration(milliseconds: 18000), vsync: this)..repeat();
  late final AnimationController _arrowController =
      AnimationController(duration: const Duration(milliseconds: 800), vsync: this)..repeat(reverse: true);
  late final Animation<double> _arrowAnimation =
      Tween<double>(begin: 0, end: 3).animate(CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut));

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _waveController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
      analyticsSource: widget.analyticsSource,
    );
  }
}

/// Opens the plans sheet over [context].
Future<void> showStandalonePlansSheet(BuildContext context, {String analyticsSource = 'usage_page'}) async {
  final title = await plansSheetTitle(context);
  if (!context.mounted) return;
  return showOmiSheet<void>(
    context: context,
    title: title,
    padding: EdgeInsets.zero,
    builder: (_) => StandalonePlansSheet(analyticsSource: analyticsSource),
  );
}
