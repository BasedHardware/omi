import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/utils/daily_summary_journey.dart';

void main() {
  const unknown = 'Unknown';

  group('buildTimelineLocations', () {
    test('empty-address pins at distinct GPS points stay distinct rows', () {
      // Regression: merging by short name collapsed every empty address to one
      // "Unknown" row spanning first→last time.
      final timeline = buildTimelineLocations([
        LocationPin(latitude: 37.7749, longitude: -122.4194, time: '08:00'),
        LocationPin(latitude: 37.7849, longitude: -122.4094, time: '10:00'),
        LocationPin(latitude: 37.8044, longitude: -122.2711, time: '13:30'),
      ], unknownLabel: unknown);

      expect(timeline, hasLength(3));
      expect(timeline.map((row) => row.shortName).toList(), [unknown, unknown, unknown]);
      expect(timeline.map((row) => row.startTime).toList(), ['08:00', '10:00', '13:30']);
      expect(timeline.map((row) => row.endTime).toList(), ['08:00', '10:00', '13:30']);
    });

    test('nearby empty-address pins still merge into one stay', () {
      final timeline = buildTimelineLocations([
        LocationPin(latitude: 37.77490, longitude: -122.41940, time: '08:00'),
        LocationPin(latitude: 37.77500, longitude: -122.41940, time: '08:20'),
      ], unknownLabel: unknown);

      expect(timeline, hasLength(1));
      expect(timeline.single.shortName, unknown);
      expect(timeline.single.startTime, '08:00');
      expect(timeline.single.endTime, '08:20');
    });

    test('named places still split when coordinates differ', () {
      final timeline = buildTimelineLocations([
        LocationPin(latitude: 37.7749, longitude: -122.4194, address: 'Home, San Francisco', time: '08:00'),
        LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '10:00'),
      ], unknownLabel: unknown);

      expect(timeline.map((row) => row.shortName).toList(), ['Home', 'Office']);
    });

    test('sorts by time before clustering', () {
      final timeline = buildTimelineLocations([
        LocationPin(latitude: 37.7849, longitude: -122.4094, time: '10:00'),
        LocationPin(latitude: 37.7749, longitude: -122.4194, time: '08:00'),
      ], unknownLabel: unknown);

      expect(timeline.first.latitude, 37.7749);
      expect(timeline.first.startTime, '08:00');
      expect(timeline.last.latitude, 37.7849);
    });
  });
}
