import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Section header for the honest capture-gap group (SCA-381): calendar events
/// that were booked but never recorded. Rendered above the day's audio rows,
/// never replacing them.
class CaptureGapHeader extends StatelessWidget {
  final int count;

  const CaptureGapHeader({super.key, required this.count});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 16, 4),
      child: Text(
        context.l10n.conversationsNotCapturedCount(count),
        style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// One compact "not captured" calendar row. Neutral greys only — brand UI keeps
/// to white/neutral accents (INV-UI-1), and this row must read as quieter than
/// a recorded conversation.
class CaptureGapListItem extends StatelessWidget {
  final CalendarCaptureGap gap;

  const CaptureGapListItem({super.key, required this.gap});

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.localeOf(context).languageCode;
    final timeStr =
        '${dateTimeFormat('h:mm a', gap.startTime.toLocal(), locale: locale)} – ${dateTimeFormat('h:mm a', gap.endTime.toLocal(), locale: locale)}';

    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Container(
        width: double.maxFinite,
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(24.0)),
        child: Padding(
          padding: const EdgeInsetsDirectional.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(12)),
                child: Icon(Icons.event_busy, color: Colors.grey.shade500, size: 20),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      gap.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      timeStr,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
