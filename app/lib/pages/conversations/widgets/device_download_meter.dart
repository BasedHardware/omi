import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Overall device-download meter for the Offline Sync status card, and the
/// bar-only form used on the recording that is actually transferring.
///
/// Percent and speed belong on the total. A recording row passes
/// [showReadout] false so it does not repeat those numbers.
class DeviceDownloadMeter extends StatelessWidget {
  const DeviceDownloadMeter({
    super.key,
    required this.fraction,
    this.speedKBps,
    this.showReadout = true,
    this.barHeight = 6,
  });

  /// 0..1. Zero or negative draws an indeterminate bar: the transfer has
  /// started, but the device has not yet reported a countable fraction.
  final double fraction;

  final double? speedKBps;

  /// Status card only. Recording rows must leave this false.
  final bool showReadout;

  final double barHeight;

  @override
  Widget build(BuildContext context) {
    final known = fraction > 0;
    final percent = (fraction.clamp(0.0, 1.0) * 100).round();
    final speed = speedKBps;
    final hasSpeed = speed != null && speed > 0;
    final readout = !showReadout
        ? null
        : !known
            ? null
            : hasSpeed
                ? context.l10n.syncCardDownloadPercentSpeed(
                    percent,
                    speed < 10 ? speed.toStringAsFixed(1) : speed.toStringAsFixed(0),
                  )
                : context.l10n.syncCardDownloadPercent(percent);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(barHeight / 2),
          child: LinearProgressIndicator(
            value: known ? fraction.clamp(0.0, 1.0) : null,
            minHeight: barHeight,
            backgroundColor: OmiColors.active == OmiPalette.light ? OmiColors.surface3 : Colors.grey.shade800,
            color: OmiColors.accent,
          ),
        ),
        if (readout != null) ...[
          const SizedBox(height: 8),
          Text(
            readout,
            style: OmiType.footnote.copyWith(color: Colors.grey.shade500),
          ),
        ],
      ],
    );
  }
}
