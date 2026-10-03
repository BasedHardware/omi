import 'package:flutter/material.dart';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';

/// On-device ring-buffer storage usage indicator, shown on the Auto Sync page
/// for firmware 3.0.20+ devices. An outlined card: title + % full, a slim ink
/// usage bar (amber ≥80%, red ≥95%), and a "used of total · free" summary line.
class DeviceStorageCard extends StatelessWidget {
  final RingStatus status;

  const DeviceStorageCard({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final used = status.usedBytes < 0 ? 0 : status.usedBytes;
    final free = status.freeBytes < 0 ? 0 : status.freeBytes;
    final total = used + free;
    final fraction = total == 0 ? 0.0 : (used / total).clamp(0.0, 1.0);
    final percent = (fraction * 100).round();
    final nearlyFull = fraction >= 0.95;

    // Ink for normal usage, like the rest of Settings; amber and red only for the near-full
    // warning and critical bands.
    final Color barColor =
        fraction >= 0.95 ? OmiColors.danger : (fraction >= 0.80 ? OmiColors.warning : OmiColors.textPrimary);

    return OmiGroupedCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(l.deviceStorageTitle, style: OmiType.body.copyWith(fontWeight: FontWeight.w500)),
              ),
              Text(
                l.deviceStoragePercentFull(percent),
                style: OmiType.subhead.copyWith(color: barColor, fontWeight: FontWeight.w600),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.sm),
          ClipRRect(
            borderRadius: OmiRadius.pillAll,
            child: LinearProgressIndicator(
              value: fraction,
              minHeight: 6,
              backgroundColor: OmiColors.surface3,
              valueColor: AlwaysStoppedAnimation<Color>(barColor),
            ),
          ),
          const SizedBox(height: OmiSpacing.sm),
          Text(
            '${l.deviceStorageUsedOfTotal(WavBytesUtil.formatBytes(used, decimals: 0), WavBytesUtil.formatBytes(total, decimals: 0))}  ·  ${l.deviceStorageFree(WavBytesUtil.formatBytes(free, decimals: 0))}',
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
          if (nearlyFull) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(l.deviceStorageNearlyFull, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
          ],
        ],
      ),
    );
  }
}
