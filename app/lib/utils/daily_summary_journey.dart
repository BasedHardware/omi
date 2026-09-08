import 'package:latlong2/latlong.dart';

import 'package:omi/backend/schema/daily_summary.dart';

/// Consecutive pins within this radius are one stay; farther pins stay distinct
/// rows even when reverse-geocoding left the address empty.
const double kJourneyMergeRadiusMeters = 100;

const Distance _distance = Distance();

class TimelineLocation {
  final String shortName;
  final double latitude;
  final double longitude;
  final String? startTime;
  String? endTime;

  TimelineLocation({
    required this.shortName,
    required this.latitude,
    required this.longitude,
    this.startTime,
    this.endTime,
  });
}

String shortLocationName(String? address, {required String unknownLabel}) {
  if (address == null || address.isEmpty) return unknownLabel;
  return address.split(',').first.trim();
}

int parseTimeToMinutes(String? timeStr) {
  if (timeStr == null || timeStr.isEmpty) return 0;
  final parts = timeStr.split(':');
  if (parts.length != 2) return 0;
  final hours = int.tryParse(parts[0]) ?? 0;
  final minutes = int.tryParse(parts[1]) ?? 0;
  return hours * 60 + minutes;
}

bool _withinMergeRadius(TimelineLocation current, LocationPin next, double radiusMeters) {
  final meters = _distance.as(
    LengthUnit.Meter,
    LatLng(current.latitude, current.longitude),
    LatLng(next.latitude, next.longitude),
  );
  return meters <= radiusMeters;
}

/// Cluster a day's pins by coordinates and time, not by empty "Unknown" names.
List<TimelineLocation> buildTimelineLocations(
  List<LocationPin> locations, {
  required String unknownLabel,
  double mergeRadiusMeters = kJourneyMergeRadiusMeters,
}) {
  if (locations.isEmpty) return [];

  final sortedLocations = List<LocationPin>.from(locations);
  sortedLocations.sort((a, b) => parseTimeToMinutes(a.time).compareTo(parseTimeToMinutes(b.time)));

  final timeline = <TimelineLocation>[];
  TimelineLocation? current;

  for (final loc in sortedLocations) {
    final name = shortLocationName(loc.address, unknownLabel: unknownLabel);
    if (current == null || !_withinMergeRadius(current, loc, mergeRadiusMeters)) {
      current = TimelineLocation(
        shortName: name,
        latitude: loc.latitude,
        longitude: loc.longitude,
        startTime: loc.time,
        endTime: loc.time,
      );
      timeline.add(current);
    } else {
      current.endTime = loc.time;
    }
  }

  return timeline;
}
