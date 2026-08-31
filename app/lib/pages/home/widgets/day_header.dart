import 'package:flutter/material.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Header of the home day view: the day's map as a backdrop, the day
/// navigator, where the day was spent, and the day's headline.
class DayHeader extends StatelessWidget {
  const DayHeader({
    super.key,
    required this.day,
    required this.conversations,
    required this.canGoForward,
    required this.onPreviousDay,
    required this.onNextDay,
    this.headline,
    this.onHeadlineTap,
    this.tileProvider,
  });

  final DateTime day;

  /// Every conversation of the day, short and discarded ones included — they
  /// still carry the locations that make up the day's map.
  final List<ServerConversation> conversations;

  final bool canGoForward;
  final VoidCallback onPreviousDay;
  final VoidCallback onNextDay;
  final String? headline;
  final VoidCallback? onHeadlineTap;

  /// Test seam: lets a widget test serve map tiles without network access.
  final TileProvider? tileProvider;

  @override
  Widget build(BuildContext context) {
    final points = dayLocationPoints(conversations);
    final place = dayPlaceLabel(conversations);
    final summary = headline?.trim();

    return Stack(
      children: [
        if (points.isNotEmpty)
          Positioned.fill(child: _DayMapBackdrop(key: ValueKey(day), points: points, tileProvider: tileProvider)),
        Padding(
          padding: EdgeInsets.fromLTRB(24, 4, 16, points.isEmpty ? 20 : 44),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Row(
                      children: [
                        _DayArrow(icon: Icons.chevron_left_rounded, onTap: onPreviousDay),
                        Flexible(
                          child: Text(
                            dayLabel(context, day),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 28,
                              fontWeight: FontWeight.w700,
                              letterSpacing: -0.6,
                            ),
                          ),
                        ),
                        _DayArrow(icon: Icons.chevron_right_rounded, onTap: canGoForward ? onNextDay : null),
                      ],
                    ),
                  ),
                  if (place != null) ...[const SizedBox(width: 8), _PlaceChip(label: place)],
                ],
              ),
              if (summary != null && summary.isNotEmpty) ...[
                const SizedBox(height: 10),
                GestureDetector(
                  onTap: onHeadlineTap,
                  child: Text(
                    summary,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Colors.white, fontSize: 19, height: 1.35, letterSpacing: -0.2),
                  ),
                ),
              ],
              if (points.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(
                  '© OpenStreetMap contributors',
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.35), fontSize: 10),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// "Today" / "Yesterday" / "Fri, Sep 5" for the day navigator.
String dayLabel(BuildContext context, DateTime day) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  if (day == today) return context.l10n.today;
  if (day == today.subtract(const Duration(days: 1))) return context.l10n.yesterday;
  return MaterialLocalizations.of(context).formatMediumDate(day);
}

/// Map pins for the day. Conversations without a usable fix are skipped.
List<LatLng> dayLocationPoints(List<ServerConversation> conversations) {
  final points = <LatLng>[];
  for (final conversation in conversations) {
    final latitude = conversation.geolocation?.latitude;
    final longitude = conversation.geolocation?.longitude;
    if (latitude == null || longitude == null) continue;
    if (!latitude.isFinite || !longitude.isFinite) continue;
    if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) continue;
    if (latitude == 0 && longitude == 0) continue;
    points.add(LatLng(latitude, longitude));
  }
  return points;
}

/// Where the day happened: the place that shows up in the most conversations.
String? dayPlaceLabel(List<ServerConversation> conversations) {
  final counts = <String, int>{};
  for (final conversation in conversations) {
    final label = shortPlaceLabel(conversation.geolocation?.address?.decodeString);
    if (label == null) continue;
    counts[label] = (counts[label] ?? 0) + 1;
  }
  if (counts.isEmpty) return null;
  return counts.entries.reduce((a, b) => b.value > a.value ? b : a).key;
}

/// The area component of a full address — the same component the conversation
/// detail map labels a pin with.
///
/// "1234 Mission St, San Francisco, CA 94110, USA" → "San Francisco": the
/// street line and the trailing zip/country parts carry no meaning at a glance,
/// so a long address collapses to the part people actually say out loud.
String? shortPlaceLabel(String? address) {
  if (address == null) return null;
  final parts = address.split(',').map((part) => part.trim()).where((part) => part.isNotEmpty).toList();
  if (parts.isEmpty) return null;
  if (parts.length >= 3) return parts[parts.length - 3];
  return parts.first;
}

class _DayArrow extends StatelessWidget {
  const _DayArrow({required this.icon, this.onTap});

  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox(
        width: 34,
        height: 40,
        child: Icon(
          icon,
          size: 26,
          color: onTap == null ? Colors.white.withValues(alpha: 0.18) : Colors.white.withValues(alpha: 0.55),
        ),
      ),
    );
  }
}

class _PlaceChip extends StatelessWidget {
  const _PlaceChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 160),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
            ),
            const SizedBox(width: 7),
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The day's map, dimmed and faded into the page so the header text stays the
/// thing you read.
class _DayMapBackdrop extends StatefulWidget {
  const _DayMapBackdrop({super.key, required this.points, this.tileProvider});

  final List<LatLng> points;
  final TileProvider? tileProvider;

  @override
  State<_DayMapBackdrop> createState() => _DayMapBackdropState();
}

class _DayMapBackdropState extends State<_DayMapBackdrop> {
  // flutter_map 7 can apply the initial camera fit without scheduling the newly
  // visible tiles, leaving the backdrop blank. An imperceptible camera move
  // after layout makes the tile layer load the fitted bounds.
  static const double _tileLoadZoomDelta = 0.000001;

  final MapController _mapController = MapController();

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  void _loadTilesAfterLayout() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final camera = _mapController.camera;
      _mapController.move(camera.center, camera.zoom + _tileLoadZoomDelta);
    });
  }

  @override
  Widget build(BuildContext context) {
    final distinctPoints = widget.points.toSet().toList();
    final singlePoint = distinctPoints.length == 1;
    final center = singlePoint ? distinctPoints.first : LatLngBounds.fromPoints(distinctPoints).center;

    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: center,
              initialZoom: 14,
              initialCameraFit: singlePoint
                  ? null
                  : CameraFit.bounds(
                      bounds: LatLngBounds.fromPoints(distinctPoints),
                      padding: const EdgeInsets.all(48),
                      maxZoom: 15,
                    ),
              interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
              keepAlive: true,
              backgroundColor: Colors.black,
              onMapReady: _loadTilesAfterLayout,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                subdomains: const ['a', 'b', 'c', 'd'],
                userAgentPackageName: 'me.omi.app',
                minNativeZoom: 0,
                maxNativeZoom: 19,
                retinaMode: RetinaMode.isHighDensity(context),
                keepBuffer: 0,
                panBuffer: 0,
                tileDisplay: const TileDisplay.instantaneous(),
                tileProvider: widget.tileProvider,
              ),
            ],
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.55),
                  Colors.black.withValues(alpha: 0.7),
                  Colors.black.withValues(alpha: 0.94),
                  Colors.black,
                ],
                stops: const [0, 0.45, 0.82, 1],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
