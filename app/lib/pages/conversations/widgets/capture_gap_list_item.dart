import 'package:omi/ui/omi_tokens.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/device_tile.dart';

/// Section header for the honest capture-gap group (SCA-381): calendar events
/// that were booked but never recorded. Rendered above the day's audio rows,
/// never replacing them.
class CaptureGapHeader extends StatelessWidget {
  final int count;

  const CaptureGapHeader({super.key, required this.count});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 2),
      child: Text(
        context.l10n.conversationsNotCapturedCount(count),
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// One compact "not captured" calendar row: a dashed, empty tile where a recorded row has its
/// device. Neutral greys only — brand UI keeps to white/neutral accents (INV-UI-1), and this row
/// must read as quieter than a recorded conversation.
class CaptureGapListItem extends StatelessWidget {
  final CalendarCaptureGap gap;

  const CaptureGapListItem({super.key, required this.gap});

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    final timeStr =
        '${dateTimeFormat('h:mm a', gap.startTime.toLocal(), locale: locale)} – ${dateTimeFormat('h:mm a', gap.endTime.toLocal(), locale: locale)}';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: DeviceTile.rowPadding),
      child: Row(
        children: [
          const DeviceTile(icon: Icons.event_busy, missing: true),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  gap.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.callout.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                ),
                const SizedBox(height: 3),
                Text(
                  timeStr,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
