import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/widgets/omi_map_preview.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  // OmiMapPreview builds proxy URLs from Env.apiBaseUrl; statics are per-isolate.
  setUpAll(() => Env.init(_TestEnvFields()));

  testWidgets('renders a map preview strip for a recap with valid locations', (tester) async {
    final summary = _summary(
      locations: [
        LocationPin(latitude: 37.7749, longitude: -122.4194),
        LocationPin(latitude: 37.7849, longitude: -122.4094),
      ],
    );

    await _pumpCard(tester, summary);

    expect(find.byKey(const ValueKey('daily_summary_map_summary-1')), findsOneWidget);
    expect(
      tester.getSize(find.byKey(const ValueKey('daily_summary_map_summary-1'))).height,
      DailySummaryCard.mapHeight,
    );

    // The card hands its pins to the shared preview widget (URL building and
    // the auth gate are covered by omi_map_preview_test).
    final preview = tester.widget<OmiMapPreview>(find.byType(OmiMapPreview));
    expect(preview.pins, hasLength(2));
    expect(preview.pins.first.latitude, 37.7749);
    expect(preview.pins.first.longitude, -122.4194);
    expect(preview.pins.last.latitude, 37.7849);
    expect(preview.pins.last.longitude, -122.4094);
  });

  testWidgets('renders a centered preview for a recap with one valid location', (tester) async {
    final summary = _summary(locations: [LocationPin(latitude: 51.5072, longitude: -0.1276)]);

    await _pumpCard(tester, summary);

    final preview = tester.widget<OmiMapPreview>(find.byType(OmiMapPreview));
    expect(preview.pins, hasLength(1));
    expect(preview.pins.single.latitude, 51.5072);
  });

  testWidgets('treats repeated coordinates as a single map location', (tester) async {
    final summary = _summary(
      locations: [
        LocationPin(latitude: 51.5072, longitude: -0.1276),
        LocationPin(latitude: 51.5072, longitude: -0.1276),
      ],
    );

    await _pumpCard(tester, summary);

    // Both pins flow to the preview; URL-side dedupe is asserted in
    // omi_map_preview_test's buildOmiStaticMapUrl cases.
    final preview = tester.widget<OmiMapPreview>(find.byType(OmiMapPreview));
    expect(preview.pins, hasLength(2));
  });

  testWidgets('shows the offline pin-dot canvas when the image cannot load', (tester) async {
    final summary = _summary(locations: [LocationPin(latitude: 37.7749, longitude: -122.4194)]);

    await _pumpCard(tester, summary);
    await tester.pumpAndSettle();

    // The test environment cannot reach the proxy and auth cannot resolve, so
    // the widget must settle on the fallback canvas rather than an error state.
    expect(find.byKey(const ValueKey('omi_map_preview_fallback')), findsWidgets);
    expect(find.byType(CachedNetworkImage), findsNothing);
    expect(find.text('Yesterday'), findsOneWidget);
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

    expect(find.byType(OmiMapPreview), findsNothing);
    expect(find.text('Yesterday'), findsOneWidget);
  });
}

Future<void> _pumpCard(WidgetTester tester, DailySummary summary) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: DailySummaryCard(summary: summary, dateLabel: 'Yesterday', onTap: () {}),
        ),
      ),
    ),
  );
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
