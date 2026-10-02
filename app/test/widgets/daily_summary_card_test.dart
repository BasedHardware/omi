import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/daily_summary_card.dart';
import 'package:omi/ui/ui.dart';
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

  testWidgets('a recap with places shows the first one on a map along the top of the card', (tester) async {
    final summary = _summary(
      locations: [
        LocationPin(latitude: 0, longitude: 0),
        LocationPin(latitude: 37.7749, longitude: -122.4194),
        LocationPin(latitude: 37.7849, longitude: -122.4094),
      ],
    );

    await _pumpCard(tester, summary);

    final map = find.byKey(const ValueKey('daily_summary_map_summary-1'));
    expect(map, findsOneWidget);
    expect(tester.getSize(map).height, DailySummaryCard.mapHeight);
    expect(tester.getRect(map).top, tester.getRect(find.byKey(const ValueKey('daily_summary_card_summary-1'))).top);
    expect(tester.getRect(find.text('Yesterday')).top, greaterThan(tester.getRect(map).bottom),
        reason: 'the date and headline sit under the map');

    // One pin, the first usable place (URL building and the auth gate are covered by
    // omi_map_preview_test).
    final preview = tester.widget<OmiMapPreview>(find.byType(OmiMapPreview));
    expect(preview.pins, hasLength(1));
    expect(preview.pins.single.latitude, 37.7749);
    expect(preview.pins.single.longitude, -122.4194);
  });

  testWidgets('the card has the glass rim, and only a recap without a map shows its emoji', (tester) async {
    await _pumpCard(tester, _summary(locations: [LocationPin(latitude: 51.5072, longitude: -0.1276)], emoji: '🌉'));
    final card = tester.widget<Container>(find.byKey(const ValueKey('daily_summary_card_summary-1')));
    final fill = card.decoration! as ShapeDecoration;
    expect(fill.color, OmiColors.surface1, reason: 'the card colour, not the controls\' glass');
    expect(fill.shadows, isNull, reason: 'content sits on the page; only controls are lifted');
    expect(card.foregroundDecoration, isA<OmiGlassRim>());
    expect(find.text('🌉'), findsNothing);

    await _pumpCard(tester, _summary(locations: const [], emoji: '🌉'));
    expect(find.text('🌉'), findsOneWidget);
  });

  testWidgets('renders a centered preview for a recap with one valid location', (tester) async {
    final summary = _summary(locations: [LocationPin(latitude: 51.5072, longitude: -0.1276)]);

    await _pumpCard(tester, summary);

    final preview = tester.widget<OmiMapPreview>(find.byType(OmiMapPreview));
    expect(preview.pins, hasLength(1));
    expect(preview.pins.single.latitude, 51.5072);
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

  testWidgets('a map card keeps a long headline to whole lines at large text sizes', (tester) async {
    for (final scale in [1.0, 1.3, 1.6]) {
      await _pumpCard(
        tester,
        _summary(
          locations: [LocationPin(latitude: 37.7749, longitude: -122.4194)],
          headline: 'Rewrite, equity, and product polish dominated a long and busy day across town',
        ),
        textScale: scale,
      );

      expect(tester.takeException(), isNull, reason: 'no overflow at ${scale}x');
      final headline = tester.widget<Text>(find.textContaining('Rewrite, equity'));
      final lineHeight = 15 * scale * 1.3;
      // The headline's box is the room above the map; the lines it may show must fit in it.
      final room = tester.getSize(find.textContaining('Rewrite, equity')).height;
      expect(headline.maxLines, inInclusiveRange(1, 2), reason: 'at ${scale}x');
      expect(headline.maxLines! * lineHeight, lessThanOrEqualTo(room + 0.5),
          reason: 'the headline shows whole lines only at ${scale}x');
      if (scale == 1.0) expect(headline.maxLines, 2, reason: 'two headline lines fit at the default size');
    }
  });
}

Future<void> _pumpCard(WidgetTester tester, DailySummary summary, {double textScale = 1.0}) async {
  await tester.pumpWidget(
    MaterialApp(
      builder: (context, child) =>
          MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)), child: child!),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
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

DailySummary _summary(
    {required List<LocationPin> locations, String headline = 'A day around the city', String emoji = '📅'}) {
  return DailySummary(
    id: 'summary-1',
    date: '2026-07-15',
    createdAt: DateTime(2026, 7, 16),
    dayEmoji: emoji,
    headline: headline,
    overview: '',
    stats: DayStats(),
    locations: locations,
  );
}
