import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_map/flutter_map.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/day_header.dart';

void main() {
  testWidgets('renders a fitted map backdrop for a day with several locations', (tester) async {
    _MemoryTileProvider.requests = 0;

    await _pumpHeader(tester, [
      _conversation('a', latitude: 37.7749, longitude: -122.4194),
      _conversation('b', latitude: 37.7849, longitude: -122.4094),
    ]);

    expect(find.byType(FlutterMap), findsOneWidget);
    final map = tester.widget<FlutterMap>(find.byType(FlutterMap));
    expect(map.options.initialCameraFit, isNotNull);
    expect(map.options.keepAlive, isTrue);

    final tileLayer = tester.widget<TileLayer>(find.byType(TileLayer));
    expect(tileLayer.keepBuffer, 0);
    expect(tileLayer.panBuffer, 0);
    expect(tileLayer.tileDisplay, isA<InstantaneousTileDisplay>());

    // The camera nudge after layout is what makes the fitted bounds actually
    // request tiles — without it the backdrop paints blank.
    expect(_MemoryTileProvider.requests, greaterThan(0));
    final tileImages = tester.widgetList<RawImage>(find.byType(RawImage)).toList();
    expect(tileImages.any((image) => image.image != null), isTrue);
  });

  testWidgets('centres the map on a day spent in one place', (tester) async {
    _MemoryTileProvider.requests = 0;

    await _pumpHeader(tester, [
      _conversation('a', latitude: 51.5072, longitude: -0.1276),
      _conversation('b', latitude: 51.5072, longitude: -0.1276),
    ]);

    final map = tester.widget<FlutterMap>(find.byType(FlutterMap));
    expect(map.options.initialCenter.latitude, 51.5072);
    expect(map.options.initialCenter.longitude, -0.1276);
    expect(map.options.initialCameraFit, isNull);
    expect(_MemoryTileProvider.requests, greaterThan(0));
  });

  testWidgets('draws no map from missing or invalid coordinates', (tester) async {
    await _pumpHeader(tester, [
      _conversation('a'),
      _conversation('b', latitude: 0, longitude: 0),
      _conversation('c', latitude: 91, longitude: 10),
      _conversation('d', latitude: 10, longitude: -181),
    ]);

    expect(find.byType(FlutterMap), findsNothing);
    expect(find.text('A day worth remembering'), findsOneWidget);
  });

  testWidgets('names the place that shows up in most of the day', (tester) async {
    await _pumpHeader(tester, [
      _conversation('a', latitude: 37.7749, longitude: -122.4194, address: '1 Mission St, San Francisco, CA, USA'),
      _conversation('b', latitude: 37.7849, longitude: -122.4094, address: '9 Valencia St, San Francisco, CA, USA'),
      _conversation('c', latitude: 37.8044, longitude: -122.2712, address: '5 Broadway, Oakland, CA, USA'),
    ]);

    expect(find.text('San Francisco'), findsOneWidget);
    expect(find.text('Oakland'), findsNothing);
  });

  test('collapses a full address to its neighbourhood component', () {
    expect(shortPlaceLabel('1234 Mission St, San Francisco, CA 94110, USA'), 'San Francisco');
    expect(shortPlaceLabel('Mission District, San Francisco, USA'), 'Mission District');
    expect(shortPlaceLabel('Berlin, Germany'), 'Berlin');
    expect(shortPlaceLabel('Berlin'), 'Berlin');
    expect(shortPlaceLabel(null), isNull);
    expect(shortPlaceLabel(''), isNull);
  });
}

Future<void> _pumpHeader(WidgetTester tester, List<ServerConversation> conversations) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        backgroundColor: Colors.black,
        body: DayHeader(
          day: DateTime(2026, 7, 15),
          conversations: conversations,
          headline: 'A day worth remembering',
          canGoForward: true,
          onPreviousDay: () {},
          onNextDay: () {},
          tileProvider: _MemoryTileProvider(),
        ),
      ),
    ),
  );
  await tester.runAsync(() => precacheImage(_MemoryTileProvider._tile, tester.element(find.byType(DayHeader))));
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 100));
}

ServerConversation _conversation(String id, {double? latitude, double? longitude, String? address}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime(2026, 7, 15, 9),
    structured: Structured('Title', 'Overview', emoji: '🧠'),
    geolocation: latitude == null ? null : Geolocation(latitude: latitude, longitude: longitude, address: address),
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
