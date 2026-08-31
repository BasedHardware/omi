import 'dart:math' as math;

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
    this.summaryAddresses = const [],
    this.topInset = 0,
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

  /// Addresses the daily summary recorded for the day. Conversations often
  /// carry coordinates without an address, so the summary is the only place a
  /// place *name* exists.
  final List<String?> summaryAddresses;

  final bool canGoForward;

  /// Height of the status bar plus the app bar. Home draws the map full-bleed
  /// under both, so the header's own text starts below them.
  final double topInset;
  final VoidCallback onPreviousDay;
  final VoidCallback onNextDay;
  final String? headline;
  final VoidCallback? onHeadlineTap;

  /// Test seam: lets a widget test serve map tiles without network access.
  final TileProvider? tileProvider;

  @override
  Widget build(BuildContext context) {
    final points = dayLocationPoints(conversations);
    final place = dayPlaceLabel(conversations, summaryAddresses: summaryAddresses);
    final summary = headline?.trim();

    final content = Padding(
      padding: EdgeInsets.fromLTRB(24, topInset + 4, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
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
          if (place != null) ...[const SizedBox(height: 10), _PlaceLabel(label: place)],
        ],
      ),
    );

    if (points.isEmpty) return content;

    // With a map the header is a place, not a caption: give it room to read as
    // one instead of a strip behind two lines of text.
    return ConstrainedBox(
      constraints: BoxConstraints(minHeight: topInset + math.min(190, MediaQuery.sizeOf(context).height * 0.22)),
      child: Stack(
        children: [
          Positioned.fill(child: _DayMapBackdrop(key: ValueKey(day), points: points, tileProvider: tileProvider)),
          content,
        ],
      ),
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

/// Where the day happened: the place that shows up in the most conversations,
/// falling back to the day summary's own pins when the conversations only
/// carried coordinates.
String? dayPlaceLabel(List<ServerConversation> conversations, {List<String?> summaryAddresses = const []}) {
  final fromConversations = _mostCommonPlace(conversations.map((c) => c.geolocation?.address));
  return fromConversations ?? _mostCommonPlace(summaryAddresses);
}

String? _mostCommonPlace(Iterable<String?> addresses) {
  final counts = <String, int>{};
  for (final address in addresses) {
    final label = shortPlaceLabel(address?.decodeString);
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

TileLayer _esriCanvasLayer(String service, TileProvider? tileProvider) {
  return TileLayer(
    urlTemplate: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/$service/MapServer/tile/{z}/{y}/{x}',
    userAgentPackageName: 'me.omi.app',
    minNativeZoom: 0,
    maxNativeZoom: 16,
    keepBuffer: 0,
    panBuffer: 0,
    tileDisplay: const TileDisplay.instantaneous(),
    tileProvider: tileProvider,
  );
}

class _PlaceLabel extends StatelessWidget {
  const _PlaceLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.5), shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 13),
          ),
        ),
      ],
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
              // Carto's basemaps now stamp "API KEY REQUIRED" across keyless
              // tiles; Esri's dark canvas serves the same look without one. Its
              // street and place names ship as a separate reference layer.
              _esriCanvasLayer('World_Dark_Gray_Base', widget.tileProvider),
              _esriCanvasLayer('World_Dark_Gray_Reference', widget.tileProvider),
            ],
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.2),
                  Colors.black.withValues(alpha: 0.45),
                  Colors.black.withValues(alpha: 0.9),
                  Colors.black,
                ],
                stops: const [0, 0.4, 0.85, 1],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
