import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/omi_map_preview.dart';

/// A recap on Home: a glass card with the day's first place on a map along the top, then the date
/// and headline. A recap without a place shows its emoji, headline and overview instead.
class DailySummaryCard extends StatelessWidget {
  static const double width = 260;
  static const double height = 160;
  static const double mapHeight = 76;

  static TextStyle get _headlineStyle => OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: 1.3);
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
    final place = summary.locations.where(_hasUsableCoordinates).firstOrNull;
    final hasMap = place != null;

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
          // A card, not a control: the page's card colour with the glass rim.
          decoration: ShapeDecoration(shape: _cardShape, color: OmiCanvas.cardOf(context)),
          // Over the map too, so the glass edge runs across its top.
          foregroundDecoration: OmiGlass.rim(_cardShape),
          child: ClipRRect(
            borderRadius: _cardRadius,
            child: Stack(
              children: [
                if (hasMap)
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    height: mapHeight,
                    child: OmiMapPreview(
                      key: ValueKey('daily_summary_map_${summary.id}'),
                      pins: [OmiMapPin(latitude: place.latitude, longitude: place.longitude)],
                      backgroundColor: OmiCanvas.cardOf(context),
                    ),
                  ),
                Positioned(
                  top: hasMap ? mapHeight : 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(14, hasMap ? 8 : 12, 14, hasMap ? 6 : 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Eyebrow: the day, so the headline can carry the story.
                        Row(
                          children: [
                            if (!hasMap && summary.dayEmoji.isNotEmpty) ...[
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
                        if (hasMap)
                          // Below the map the band is short: whole lines only (at most two), so large
                          // text ends on an ellipsis instead of clipping through a line.
                          Expanded(
                            child: LayoutBuilder(builder: (context, box) {
                              final line = MediaQuery.textScalerOf(context).scale(_headlineStyle.fontSize!) *
                                  _headlineStyle.height!;
                              final lines = math.min(2, (box.maxHeight / line).floor());
                              if (lines < 1) return const SizedBox.shrink();
                              return Text(summary.headline,
                                  style: _headlineStyle, maxLines: lines, overflow: TextOverflow.ellipsis);
                            }),
                          )
                        else
                          Flexible(
                            child: Text(
                              summary.headline,
                              style: _headlineStyle,
                              maxLines: 3,
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
  static const ShapeBorder _cardShape = RoundedRectangleBorder(borderRadius: _cardRadius);

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
