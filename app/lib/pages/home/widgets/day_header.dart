import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/local_recording.dart';
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
    this.recordings = const [],
    this.summaryAddresses = const [],
    this.topInset = 0,
    required this.onPreviousDay,
    required this.onNextDay,
    this.headline,
    this.onHeadlineTap,
    this.onPickDay,
    this.tileProvider,
    this.navigable = true,
  });

  final DateTime day;

  /// Every conversation of the day, short and discarded ones included — they
  /// still carry the locations that make up the day's map.
  final List<ServerConversation> conversations;

  /// Transcribe Later captures for the day. They carry a start-location
  /// snapshot of their own, so a day spent recording offline still has a map.
  final List<LocalRecording> recordings;

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

  /// Tapping the day name jumps to a date instead of stepping there one
  /// arrow press at a time.
  final VoidCallback? onPickDay;

  /// Test seam: lets a widget test serve map tiles without network access.
  final TileProvider? tileProvider;

  /// A first run has no other day worth going to, so the arrows and the date
  /// picker would only lead to more empty days. The day still names itself.
  final bool navigable;

  @override
  Widget build(BuildContext context) {
    final points = dayLocationPoints(conversations, recordings: recordings);
    final place = dayPlaceLabel(conversations, summaryAddresses: summaryAddresses, recordings: recordings);
    final summary = headline?.trim();

    final content = Padding(
      // The day name clears the app bar controls rather than sitting flush
      // under them, and the headline gets room before the first conversation.
      padding: EdgeInsets.fromLTRB(24, topInset + 16, 16, 26),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (navigable) _DayArrow(icon: Icons.chevron_left_rounded, onTap: onPreviousDay),
              Flexible(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: navigable ? onPickDay : null,
                  child: Text(
                    dayLabel(context, day),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -0.4,
                    ),
                  ),
                ),
              ),
              if (navigable) _DayArrow(icon: Icons.chevron_right_rounded, onTap: canGoForward ? onNextDay : null),
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
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.92),
                  fontSize: 17,
                  height: 1.35,
                  letterSpacing: -0.1,
                ),
              ),
            ),
          ],
          if (place != null) ...[const SizedBox(height: 10), _PlaceLabel(label: place)],
        ],
      ),
    );

    // Days differ in whether they have a map at all and in how tall their
    // headline runs, so stepping between them used to cut the map away and snap
    // the header to its new height in one frame. Keep one structure and let the
    // two things that actually change — the backdrop and the height — animate.
    return AnimatedSize(
      duration: _dayTransition,
      curve: Curves.easeOutCubic,
      alignment: Alignment.topCenter,
      // Defaults to Clip.hardEdge, which would cut off the backdrop's bleed
      // above the header and leave the overscroll showing the page again. The
      // viewport still clips what is genuinely off screen.
      clipBehavior: Clip.none,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: points.isEmpty ? 0 : topInset + math.min(96, MediaQuery.sizeOf(context).height * 0.11),
        ),
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned(
              // Pull-to-refresh translates the whole sliver down. With nothing
              // above the header there is only the black page up there, so the
              // backdrop reaches past the top of the screen to cover the pull.
              top: -_overscrollBleed,
              left: 0,
              right: 0,
              bottom: 0,
              child: AnimatedSwitcher(
                duration: _dayTransition,
                child: points.isEmpty
                    ? const SizedBox.shrink(key: ValueKey('day-map-none'))
                    : _DayMapBackdrop(
                        // Deliberately not keyed by day. Re-keying built a
                        // fresh map for every day, so stepping days cross-faded
                        // a loaded map out and an empty one in and the tiles
                        // popped back as they downloaded — the flicker. One map
                        // persists across days and re-frames itself instead
                        // (see didUpdateWidget), keeping the tiles it already
                        // has. The switcher is left to do what it is for: days
                        // with a map versus days without one.
                        key: const ValueKey('day-map'),
                        points: points,
                        topBleed: _overscrollBleed,
                        tileProvider: tileProvider,
                      ),
              ),
            ),
            content,
          ],
        ),
      ),
    );
  }
}

/// Long enough to read as a transition between two days, short enough that
/// paging through a week with the arrows never feels held up.
const Duration _dayTransition = Duration(milliseconds: 260);

/// How far the map reaches above the header, off screen, so a pull-to-refresh
/// overscroll drags map into view instead of the page behind it.
const double _overscrollBleed = 220;

/// "Today" / "Yesterday" / "Fri, Sep 5" for the day navigator.
String dayLabel(BuildContext context, DateTime day) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  if (day == today) return context.l10n.today;
  if (day == today.subtract(const Duration(days: 1))) return context.l10n.yesterday;
  return MaterialLocalizations.of(context).formatMediumDate(day);
}

/// Map pins for the day, from its conversations and from any Transcribe Later
/// captures still waiting to be uploaded. Anything without a usable fix is
/// skipped.
List<LatLng> dayLocationPoints(
  List<ServerConversation> conversations, {
  List<LocalRecording> recordings = const [],
}) {
  final points = <LatLng>[];
  for (final conversation in conversations) {
    _addPoint(points, conversation.geolocation?.latitude, conversation.geolocation?.longitude);
  }
  for (final recording in recordings) {
    _addPoint(points, recording.geolocation?.latitude, recording.geolocation?.longitude);
  }
  return points;
}

void _addPoint(List<LatLng> points, double? latitude, double? longitude) {
  if (latitude == null || longitude == null) return;
  if (!latitude.isFinite || !longitude.isFinite) return;
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return;
  if (latitude == 0 && longitude == 0) return;
  points.add(LatLng(latitude, longitude));
}

/// Where the day happened: the place that shows up in the most conversations,
/// falling back to the day summary's own pins when the conversations only
/// carried coordinates.
String? dayPlaceLabel(
  List<ServerConversation> conversations, {
  List<String?> summaryAddresses = const [],
  List<LocalRecording> recordings = const [],
}) {
  return _mostCommonPlace(conversations.map((c) => c.geolocation?.address)) ??
      _mostCommonPlace(recordings.map((r) => r.geolocation?.address)) ??
      _mostCommonPlace(summaryAddresses);
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
    // Never even request a tile that would carry labels.
    maxNativeZoom: 14,
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
  const _DayMapBackdrop({super.key, required this.points, required this.topBleed, this.tileProvider});

  final List<LatLng> points;

  /// Height drawn above the header, off screen until an overscroll drags it in.
  final double topBleed;

  final TileProvider? tileProvider;

  @override
  State<_DayMapBackdrop> createState() => _DayMapBackdropState();
}

class _DayMapBackdropState extends State<_DayMapBackdrop> {
  // flutter_map 7 can apply the initial camera fit without scheduling the newly
  // visible tiles, leaving the backdrop blank. An imperceptible camera move
  // after layout makes the tile layer load the fitted bounds.
  static const double _tileLoadZoomDelta = 0.000001;

  // Esri's dark canvas bakes road and place names into the *base* tiles from
  // zoom 15 up (its separate reference layer is not the only source). Capping
  // the camera and the tiles below that keeps the backdrop wordless.
  static const double _labelFreeMaxZoom = 14;
  static const double _singlePointZoom = _labelFreeMaxZoom;
  static const double _boundsMaxZoom = _labelFreeMaxZoom;
  static const EdgeInsets _boundsPadding = EdgeInsets.all(48);

  final MapController _mapController = MapController();

  @override
  void didUpdateWidget(covariant _DayMapBackdrop oldWidget) {
    super.didUpdateWidget(oldWidget);
    // FlutterMap applies its camera fit once, at creation. A day that gains or
    // moves a location while it is on screen keeps the same State (the key is
    // the day), so without this the backdrop stays framed on the old points.
    if (!listEquals(oldWidget.points, widget.points)) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _fitToPoints());
    }
  }

  void _fitToPoints() {
    if (!mounted) return;
    final distinctPoints = widget.points.toSet().toList();
    if (distinctPoints.isEmpty) return;
    if (distinctPoints.length == 1) {
      _mapController.move(distinctPoints.first, _singlePointZoom);
      return;
    }
    _mapController.fitCamera(
      CameraFit.bounds(
        bounds: LatLngBounds.fromPoints(distinctPoints),
        padding: _boundsPadding,
        maxZoom: _boundsMaxZoom,
      ),
    );
  }

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  void _loadTilesAfterLayout() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final camera = _mapController.camera;
      // Nudging *up* from the cap is clamped straight back to it, which is no
      // camera change and schedules no tiles — and the cap is exactly where a
      // single-location day lands, so that is the common case, not the edge.
      final nudged =
          camera.zoom >= _labelFreeMaxZoom ? camera.zoom - _tileLoadZoomDelta : camera.zoom + _tileLoadZoomDelta;
      _mapController.move(camera.center, nudged);
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
              initialZoom: _singlePointZoom,
              initialCameraFit: singlePoint
                  ? null
                  : CameraFit.bounds(
                      bounds: LatLngBounds.fromPoints(distinctPoints),
                      padding: _boundsPadding,
                      maxZoom: _boundsMaxZoom,
                    ),
              maxZoom: _labelFreeMaxZoom,
              interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
              keepAlive: true,
              backgroundColor: Colors.black,
              onMapReady: _loadTilesAfterLayout,
            ),
            children: [
              // Carto's basemaps now stamp "API KEY REQUIRED" across keyless
              // tiles; Esri's dark canvas serves the same look without one. Its
              // reference (place-name) layer is left off and the zoom is capped
              // at _labelFreeMaxZoom: the backdrop is a sense of place, not a
              // map to read, and names competed with the text sitting over them.
              _esriCanvasLayer('World_Dark_Gray_Base', widget.tileProvider),
            ],
          ),
          // The scrim is anchored to the header, not to the backdrop: the bleed
          // above it stays at the top alpha so the fade lands in the same place
          // whether or not the user is pulling the list down.
          LayoutBuilder(
            builder: (context, constraints) {
              final height = constraints.maxHeight;
              final bleed = height <= 0 ? 0.0 : (widget.topBleed / height).clamp(0.0, 0.9);
              double at(double headerStop) => bleed + headerStop * (1 - bleed);
              return DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withValues(alpha: 0.2),
                      Colors.black.withValues(alpha: 0.2),
                      Colors.black.withValues(alpha: 0.45),
                      Colors.black.withValues(alpha: 0.9),
                      Colors.black,
                    ],
                    stops: [0, at(0), at(0.4), at(0.85), 1],
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}
