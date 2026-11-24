import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// One determinate bar for the whole sync: Omi → phone, upload, transcribe.
///
/// Each finished step counts as a third and the active step adds its [fraction], so the bar only
/// ever fills left to right across the sync. A null [fraction] means the active step has started
/// but has no measurable amount yet; the bar then holds at the start of that step.
class SyncStepBar extends StatelessWidget {
  const SyncStepBar({super.key, required this.step, required this.fraction});

  final SyncStep step;
  final double? fraction;

  @override
  Widget build(BuildContext context) {
    final track = OmiColors.active == OmiPalette.light ? OmiColors.surface3 : Colors.grey.shade800;
    final within = (fraction ?? 0).clamp(0.0, 1.0);
    final value = (step.index + within) / SyncStep.values.length;

    return ClipRRect(
      borderRadius: BorderRadius.circular(OmiRadius.sm),
      child: LinearProgressIndicator(
        value: value,
        minHeight: 6,
        backgroundColor: track,
        color: OmiColors.accent,
      ),
    );
  }
}
