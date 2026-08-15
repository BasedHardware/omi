import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_map/flutter_map.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';

void main() {
  testWidgets('renders journey locations as compact accessible map rows', (tester) async {
    final semantics = tester.ensureSemantics();

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(summaryId: 'summary-1', summary: _summary(), tileProvider: _MemoryTileProvider()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    final firstRow = find.byKey(const ValueKey('daily_summary_location_row_0'));
    final secondRow = find.byKey(const ValueKey('daily_summary_location_row_1'));
    final contentWidth = tester.getSize(find.byType(Scaffold)).width - 40;

    expect(firstRow, findsOneWidget);
    expect(secondRow, findsOneWidget);
    expect(tester.getSize(firstRow).width, contentWidth);
    expect(tester.getSize(firstRow).height, lessThan(60));
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Office'), findsOneWidget);

    final rowSemantics = tester.widget<Semantics>(find.ancestor(of: firstRow, matching: find.byType(Semantics)).first);
    expect(rowSemantics.properties.label, 'Home, 8AM');
    expect(rowSemantics.properties.button, isTrue);
    expect(rowSemantics.properties.onTap, isNotNull);
    semantics.dispose();
  });

  testWidgets('empty-address pins at distinct GPS points render as separate Unknown rows', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: ThemeData.dark(),
        home: DailySummaryDetailPage(
          summaryId: 'summary-empty-addr',
          summary: _summary(
            locations: [
              LocationPin(latitude: 37.7749, longitude: -122.4194, time: '08:00'),
              LocationPin(latitude: 37.7849, longitude: -122.4094, time: '10:00'),
            ],
          ),
          tileProvider: _MemoryTileProvider(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));

    expect(find.byKey(const ValueKey('daily_summary_location_row_0')), findsOneWidget);
    expect(find.byKey(const ValueKey('daily_summary_location_row_1')), findsOneWidget);
    expect(find.byKey(const ValueKey('daily_summary_location_row_2')), findsNothing);
    expect(find.text('Unknown'), findsNWidgets(2));
  });
}

DailySummary _summary({List<LocationPin>? locations}) {
  return DailySummary(
    id: 'summary-1',
    date: '2026-07-15',
    createdAt: DateTime(2026, 7, 16),
    headline: 'A day around the city',
    overview: 'A productive day.',
    stats: DayStats(totalConversations: 1, totalDurationMinutes: 30),
    locations: locations ??
        [
          LocationPin(latitude: 37.7749, longitude: -122.4194, address: 'Home, San Francisco', time: '08:00'),
          LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '10:00'),
        ],
  );
}

class _MemoryTileProvider extends TileProvider {
  static final _tile = MemoryImage(
    base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='),
  );

  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) => _tile;
}
