import 'package:flutter/material.dart';

import 'package:omi/services/capture/capture_continuity_monitor.dart';
import 'package:omi/ui/ui.dart';

/// Debug and TestFlight builds only: a connected pendant whose audio nobody
/// records. The monitor raises the alert only in those builds, so store users
/// never see this, and the text is deliberately not localized (dogfood
/// diagnostics, like the debug log tools).
class CaptureContinuityDogfoodBanner extends StatelessWidget {
  const CaptureContinuityDogfoodBanner({super.key, this.monitor});

  final CaptureContinuityMonitor? monitor;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<CaptureContinuityAlert?>(
      valueListenable: (monitor ?? CaptureContinuityMonitor.instance).dogfoodAlert,
      builder: (context, alert, _) {
        if (alert == null) return const SizedBox.shrink();
        final minutes = DateTime.now().difference(alert.since).inMinutes.clamp(1, 24 * 60);
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: OmiErrorState(
            title: 'Dogfood: pendant audio is not being recorded',
            message: 'Your pendant is connected, but capture has been off for about $minutes min. '
                'Share Debug Logs now, then force-quit and reopen Omi.',
          ),
        );
      },
    );
  }
}
