import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/theme/app_theme.dart';

final _timeFormat = DateFormat('h:mm a');
final _weekdayTimeFormat = DateFormat('EEE h:mm a');
final _dateTimeFormat = DateFormat('MMM d, h:mm a');

/// One conversation row in the Meetings sub-tab. Tap pushes the detail
/// screen. Visual: title (1 line) → overview (2 lines, truncates) → meta
/// strip with timestamp + segment count + starred glyph.
class ConversationRow extends StatelessWidget {
  const ConversationRow({
    super.key,
    required this.item,
    required this.onTap,
  });

  final ConversationItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final hasOverview = item.overview.trim().isNotEmpty;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppStyles.spacingS,
          vertical: AppStyles.spacingM,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    item.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                      height: 1.3,
                    ),
                  ),
                ),
                const SizedBox(width: AppStyles.spacingS),
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    _timeLabel(item.createdAt),
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textTertiary,
                    ),
                  ),
                ),
              ],
            ),
            if (hasOverview) ...[
              const SizedBox(height: 2),
              Text(
                item.overview.trim(),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textTertiary,
                  height: 1.4,
                ),
              ),
            ],
            const SizedBox(height: 6),
            DefaultTextStyle.merge(
              style: const TextStyle(
                fontSize: 11,
                color: AppColors.textQuaternary,
                fontWeight: FontWeight.w500,
                letterSpacing: 0.2,
              ),
              child: Row(
                children: [
                  if (item.starred) ...[
                    const Icon(Icons.star_rounded, size: 12, color: AppColors.warningColor),
                    const SizedBox(width: 4),
                    const Text('Starred'),
                    const SizedBox(width: AppStyles.spacingS),
                  ],
                  if (item.actionItemCount > 0) ...[
                    Text('${item.actionItemCount} action${item.actionItemCount == 1 ? '' : 's'}'),
                    const SizedBox(width: AppStyles.spacingS),
                  ],
                  if (item.segmentCount > 0)
                    Text('${item.segmentCount} turn${item.segmentCount == 1 ? '' : 's'}'),
                  if (item.category != null && item.category!.isNotEmpty) ...[
                    const SizedBox(width: AppStyles.spacingS),
                    Text(item.category!.toUpperCase()),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _timeLabel(DateTime? d) {
    if (d == null) return '';
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final dayStart = DateTime(d.year, d.month, d.day);
    final diff = today.difference(dayStart).inDays;
    if (diff < 1) return _timeFormat.format(d);
    if (diff < 7) return _weekdayTimeFormat.format(d);
    return _dateTimeFormat.format(d);
  }
}
