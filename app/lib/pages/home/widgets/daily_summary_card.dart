import 'package:flutter/material.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/omi_map_preview.dart';

class DailySummaryCard extends StatelessWidget {
  static const double width = 260;
  static const double height = 180;
  static const double mapHeight = 96;
  static const double radius = 20;

  const DailySummaryCard({
    super.key,
    required this.summary,
    required this.dateLabel,
    required this.onTap,
  });

  final DailySummary summary;
  final String dateLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final locations = summary.locations.where(_hasUsableCoordinates).toList();
    final hasMap = locations.isNotEmpty;

    return Semantics(
      button: true,
      label: dateLabel,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          key: ValueKey('daily_summary_card_${summary.id}'),
          width: width,
          height: height,
          margin: const EdgeInsets.only(right: 12),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: _cardRadius),
          child: ClipRRect(
            borderRadius: _cardRadius,
            child: Stack(
              children: [
                if (hasMap)
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: mapHeight,
                    child: OmiMapPreview(
                      key: ValueKey('daily_summary_map_${summary.id}'),
                      pins: [
                        for (final location in locations)
                          OmiMapPin(latitude: location.latitude, longitude: location.longitude),
                      ],
                      backgroundColor: OmiColors.surface1,
                    ),
                  ),
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: hasMap ? mapHeight : 0,
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(14, hasMap ? 10 : 12, 14, hasMap ? 4 : 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Eyebrow: the day, so the headline can carry the story.
                        Row(
                          children: [
                            if (summary.dayEmoji.isNotEmpty) ...[
                              Text(summary.dayEmoji, style: OmiType.footnote),
                              const SizedBox(width: 6),
                            ],
                            Flexible(
                              child: Text(
                                dateLabel,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: OmiType.footnote
                                    .copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Flexible(
                          child: Text(
                            summary.headline,
                            style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: 1.3),
                            maxLines: hasMap ? 2 : 3,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (!hasMap && summary.overview.trim().isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Expanded(
                            // As many whole lines as the card has room for, ending on an ellipsis.
                            child: LayoutBuilder(builder: (context, box) {
                              final style = OmiType.footnote.copyWith(color: OmiColors.textSecondary, height: 1.35);
                              final line = MediaQuery.textScalerOf(context).scale(style.fontSize!) * style.height!;
                              final lines = (box.maxHeight / line).floor();
                              if (lines < 1) return const SizedBox.shrink();
                              return Text(
                                summary.overview.trim(),
                                style: style,
                                maxLines: lines,
                                overflow: TextOverflow.ellipsis,
                              );
                            }),
                          ),
                        ] else if (!hasMap) ...[
                          const Spacer(),
                          if (_statsLine(context) case final stats?)
                            Text(
                              stats,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                            ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// "6 conversations · 2 tasks" for a recap with nothing else to show below its headline.
  String? _statsLine(BuildContext context) {
    final l10n = context.l10n;
    final parts = [
      if (summary.stats.totalConversations > 0) l10n.conversationCount(summary.stats.totalConversations),
      if (summary.stats.actionItemsCount > 0) l10n.taskCount(summary.stats.actionItemsCount),
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }

  static const BorderRadius _cardRadius = BorderRadius.all(Radius.circular(radius));

  static bool _hasUsableCoordinates(LocationPin location) {
    final latitude = location.latitude;
    final longitude = location.longitude;
    return latitude.isFinite &&
        longitude.isFinite &&
        latitude >= -90 &&
        latitude <= 90 &&
        longitude >= -180 &&
        longitude <= 180 &&
        (latitude != 0 || longitude != 0);
  }
}
