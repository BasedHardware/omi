import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_map/flutter_map.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';

void main() {
  testWidgets('renders a visible fitted map for a recap with valid locations', (tester) async {
    _MemoryTileProvider.requests = 0;
    final summary = _summary(
      locations: [
        LocationPin(latitude: 37.7749, longitude: -122.4194),
        LocationPin(latitude: 37.7849, longitude: -122.4094),
      ],
    );

    await _pumpCard(tester, summary);

    expect(find.byKey(const ValueKey('daily_summary_map_summary-1')), findsOneWidget);
    expect(find.byType(FlutterMap), findsOneWidget);
    expect(
        tester.getSize(find.byKey(const ValueKey('daily_summary_map_summary-1'))).height, DailySummaryCard.mapHeight);

    final map = tester.widget<FlutterMap>(find.byType(FlutterMap));
    expect(map.options.initialCameraFit, isNotNull);
    expect(map.options.keepAlive, isTrue);

    final tileLayer = tester.widget<TileLayer>(find.byType(TileLayer));
    expect(tileLayer.keepBuffer, 0);
    expect(tileLayer.panBuffer, 0);
    expect(tileLayer.tileDisplay, isA<InstantaneousTileDisplay>());

    final markerLayer = tester.widget<MarkerLayer>(find.byType(MarkerLayer));
    expect(markerLayer.markers, hasLength(2));
    final tileImages = tester.widgetList<RawImage>(find.byType(RawImage)).toList();
    expect(_MemoryTileProvider.requests, greaterThan(0));
    expect(tileImages, isNotEmpty);
    expect(tileImages.any((image) => image.image != null), isTrue);
  });

  testWidgets('renders a centered map for a recap with one valid location', (tester) async {
    _MemoryTileProvider.requests = 0;
    final summary = _summary(locations: [LocationPin(latitude: 51.5072, longitude: -0.1276)]);

    await _pumpCard(tester, summary);

    final map = tester.widget<FlutterMap>(find.byType(FlutterMap));
    expect(map.options.initialCenter.latitude, 51.5072);
    expect(map.options.initialCenter.longitude, -0.1276);
    expect(map.options.initialCameraFit, isNull);
    expect(_MemoryTileProvider.requests, greaterThan(0));
    expect(tester.widgetList<RawImage>(find.byType(RawImage)).any((image) => image.image != null), isTrue);
  });

  testWidgets('treats repeated coordinates as a single map location', (tester) async {
    final summary = _summary(
      locations: [
        LocationPin(latitude: 51.5072, longitude: -0.1276),
        LocationPin(latitude: 51.5072, longitude: -0.1276),
      ],
    );

    await _pumpCard(tester, summary);

    final map = tester.widget<FlutterMap>(find.byType(FlutterMap));
    expect(map.options.initialCenter.latitude, 51.5072);
    expect(map.options.initialCenter.longitude, -0.1276);
    expect(map.options.initialCameraFit, isNull);
  });

  testWidgets('does not build a map from missing or invalid coordinates', (tester) async {
    final summary = _summary(
      locations: [
        LocationPin(latitude: 0, longitude: 0),
        LocationPin(latitude: 91, longitude: 10),
        LocationPin(latitude: 10, longitude: -181),
      ],
    );

    await _pumpCard(tester, summary);

    expect(find.byType(FlutterMap), findsNothing);
    expect(find.text('Yesterday'), findsOneWidget);
  });
}

Future<void> _pumpCard(WidgetTester tester, DailySummary summary) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: DailySummaryCard(
            summary: summary,
            dateLabel: 'Yesterday',
            onTap: () {},
            tileProvider: _MemoryTileProvider(),
          ),
        ),
      ),
    ),
  );
  await tester.runAsync(
    () => precacheImage(_MemoryTileProvider._tile, tester.element(find.byType(DailySummaryCard))),
  );
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 100));
}

DailySummary _summary({required List<LocationPin> locations}) {
  return DailySummary(
    id: 'summary-1',
    date: '2026-07-15',
    createdAt: DateTime(2026, 7, 16),
    headline: 'A day around the city',
    overview: '',
    stats: DayStats(),
    locations: locations,
  );
}

class _MemoryTileProvider extends TileProvider {
  static int requests = 0;
  static final _tile = MemoryImage(
    base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='),
  );

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) {
    requests++;
    return _tile;
  }
}
