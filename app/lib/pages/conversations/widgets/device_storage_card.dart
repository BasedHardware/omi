import 'package:flutter/material.dart';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// On-device ring-buffer storage usage indicator, shown on the Auto Sync page
/// for firmware 3.0.20+ devices. Compact card: title + % full, a slim usage
/// bar (amber ≥80%, red ≥95%), and a "used of total · free" summary line.
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

    // Neutral white for normal usage (brand INV-UI-1: white/neutral accents);
    // amber/red are reserved for the near-full warning/critical bands.
    final Color barColor = fraction >= 0.95
        ? ResponsiveHelper.errorColor
        : (fraction >= 0.80 ? ResponsiveHelper.warningColor : Colors.white);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  l.deviceStorageTitle,
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                ),
              ),
              Text(
                l.deviceStoragePercentFull(percent),
                style: TextStyle(color: barColor, fontSize: 14, fontWeight: FontWeight.w600),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: fraction,
              minHeight: 6,
              backgroundColor: Colors.grey.shade800,
              valueColor: AlwaysStoppedAnimation<Color>(barColor),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            '${l.deviceStorageUsedOfTotal(WavBytesUtil.formatBytes(used, decimals: 0), WavBytesUtil.formatBytes(total, decimals: 0))}  ·  ${l.deviceStorageFree(WavBytesUtil.formatBytes(free, decimals: 0))}',
            style: TextStyle(color: Colors.grey.shade500, fontSize: 13, fontWeight: FontWeight.w400),
          ),
          if (nearlyFull) ...[
            const SizedBox(height: 8),
            Text(
              l.deviceStorageNearlyFull,
              style: const TextStyle(color: ResponsiveHelper.errorColor, fontSize: 13, fontWeight: FontWeight.w400),
            ),
          ],
        ],
      ),
    );
  }
}
