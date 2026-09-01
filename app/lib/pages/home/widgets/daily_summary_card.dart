import 'package:flutter/material.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'package:omi/backend/schema/daily_summary.dart';

class DailySummaryCard extends StatelessWidget {
  static const double width = 260;
  static const double height = 180;
  static const double mapHeight = 96;

  const DailySummaryCard({
    super.key,
    required this.summary,
    required this.dateLabel,
    required this.onTap,
    this.tileProvider,
  });

  final DailySummary summary;
  final String dateLabel;
  final VoidCallback onTap;
  final TileProvider? tileProvider;

  @override
  Widget build(BuildContext context) {
    final locations = summary.locations.where(_hasUsableCoordinates).toList();
    final hasMap = locations.isNotEmpty;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        key: ValueKey('daily_summary_card_${summary.id}'),
        width: width,
        height: height,
        margin: const EdgeInsets.only(right: 12),
        decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(20)),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: Stack(
            children: [
              if (hasMap)
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: mapHeight,
                  child: _DailySummaryCardMap(
                    key: ValueKey('daily_summary_map_${summary.id}'),
                    locations: locations,
                    tileProvider: tileProvider,
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
                    style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35),
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
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(50),
                  ),
                  child: Text(dateLabel, style: const TextStyle(color: Color(0xFFBBBCC2), fontSize: 11)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

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

class _DailySummaryCardMap extends StatefulWidget {
  const _DailySummaryCardMap({super.key, required this.locations, this.tileProvider});

  final List<LocationPin> locations;
  final TileProvider? tileProvider;

  @override
  State<_DailySummaryCardMap> createState() => _DailySummaryCardMapState();
}

class _DailySummaryCardMapState extends State<_DailySummaryCardMap> {
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
      // flutter_map 7 can apply the initial camera fit after creating its first
      // tile set without scheduling the newly visible tiles to load. An
      // imperceptible camera event makes the tile layer load the fitted bounds.
      _mapController.move(camera.center, camera.zoom + _tileLoadZoomDelta);
    });
  }

  @override
  Widget build(BuildContext context) {
    final points = widget.locations.map((location) => LatLng(location.latitude, location.longitude)).toList();
    final distinctPoints = points.toSet().toList();
    final singleLocation = distinctPoints.length == 1;
    final center = singleLocation ? distinctPoints.first : LatLngBounds.fromPoints(distinctPoints).center;
    final cameraFit = singleLocation
        ? null
        : CameraFit.bounds(bounds: LatLngBounds.fromPoints(distinctPoints), padding: const EdgeInsets.all(18));

    final markers = points
        .map(
          (point) => Marker(
            point: point,
            width: 22,
            height: 22,
            child: Container(
              decoration: const BoxDecoration(color: Colors.deepPurple, shape: BoxShape.circle),
              child: const Icon(Icons.location_on, color: Colors.white, size: 13),
            ),
          ),
        )
        .toList();

    return IgnorePointer(
      child: FlutterMap(
        mapController: _mapController,
        options: MapOptions(
          initialCenter: center,
          initialZoom: singleLocation ? 13 : 12,
          initialCameraFit: cameraFit,
          interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
          keepAlive: true,
          backgroundColor: const Color(0xFF1F1F25),
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
          MarkerLayer(markers: markers),
        ],
      ),
    );
  }
}
