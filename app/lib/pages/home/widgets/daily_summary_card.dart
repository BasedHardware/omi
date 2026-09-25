import 'package:flutter/material.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/ui/ui.dart';
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
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: _cardRadius),
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
                    padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
                    child: Text(
                      summary.headline,
                      style: OmiType.subhead.copyWith(height: 1.35),
                      maxLines: hasMap ? 3 : 5,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
                Positioned(
                  bottom: 10,
                  right: 10,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration:
                        BoxDecoration(color: Colors.black.withValues(alpha: 0.55), borderRadius: OmiRadius.pillAll),
                    child: Text(dateLabel, style: OmiType.caption.copyWith(color: OmiColors.textSecondary)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
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
