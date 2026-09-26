import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/env/env.dart';
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

  test('buildOmiStaticMapUrl targets the authed backend proxy with quantized pins', () {
    final url = buildOmiStaticMapUrl(
      pins: const [OmiMapPin(latitude: 37.77494, longitude: -122.41941)],
      width: 260,
      height: 96,
    );

    expect(url, startsWith('${Env.apiBaseUrl}v1/static-map?pins='));
    expect(Uri.decodeQueryComponent(url.split('pins=')[1].split('&')[0]), '37.7749,-122.4194');
    expect(url, contains('width=260'));
    expect(url, contains('height=96'));
  });

  test('buildOmiStaticMapUrl drops pins that quantize onto an included pin', () {
    final url = buildOmiStaticMapUrl(
      pins: const [
        OmiMapPin(latitude: 51.50721, longitude: -0.12763),
        OmiMapPin(latitude: 51.50719, longitude: -0.12761), // same ~11m cell
      ],
      width: 100,
      height: 100,
    );

    expect(Uri.decodeQueryComponent(url.split('pins=')[1].split('&')[0]), '51.5072,-0.1276');
  });

  test('buildOmiStaticMapUrl caps the pin count at the server limit', () {
    final url = buildOmiStaticMapUrl(
      pins: [for (var i = 0; i < 80; i++) OmiMapPin(latitude: i / 10, longitude: 0)],
      width: 100,
      height: 100,
    );

    final pins = Uri.decodeQueryComponent(url.split('pins=')[1].split('&')[0]).split('|');
    expect(pins, hasLength(kOmiMapPreviewMaxPins));
  });

  testWidgets('renders the offline pin-dot canvas while loading and on failure', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 200,
            height: 100,
            child: OmiMapPreview(pins: [OmiMapPin(latitude: 37.7749, longitude: -122.4194)]),
          ),
        ),
      ),
    );

    // Placeholder state is the fallback canvas — never a spinner or error.
    expect(find.byKey(const ValueKey('omi_map_preview_fallback')), findsOneWidget);
    await tester.pumpAndSettle();
    // The test env cannot reach the proxy (and auth cannot resolve here), so
    // both the auth gate and the error path keep the canvas.
    expect(find.byKey(const ValueKey('omi_map_preview_fallback')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('no network image until the auth header resolves; canvas holds the frame', (tester) async {
    // Regression: firing the authed request before the header resolved 401'd,
    // and the URL-derived image cache key never re-fetched — a permanent
    // fallback. The widget must render only the canvas until auth resolves.
    final headerCompleter = Completer<String>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 200,
            height: 100,
            child: OmiMapPreview(
              pins: const [OmiMapPin(latitude: 37.7749, longitude: -122.4194)],
              authHeaderProvider: () => headerCompleter.future,
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('omi_map_preview_fallback')), findsOneWidget);
    expect(find.byType(CachedNetworkImage), findsNothing);

    headerCompleter.complete('Bearer test-token');
    // One frame delivers the header through the async resolver, the next
    // rebuilds with the authed image.
    await tester.pump();
    await tester.pump();

    final image = tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage));
    expect(image.imageUrl, contains('/v1/static-map?pins='));
    expect(image.httpHeaders, containsPair('Authorization', 'Bearer test-token'));
  });

  testWidgets('empty pins render only the fallback canvas', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(width: 200, height: 100, child: OmiMapPreview(pins: [])),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('omi_map_preview_fallback')), findsOneWidget);
    expect(find.byType(CachedNetworkImage), findsNothing);
  });

  testWidgets('an injected test URL is used verbatim instead of the proxy URL', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 200,
            height: 100,
            child:
                OmiMapPreview(pins: [OmiMapPin(latitude: 1, longitude: 2)], imageUrl: 'https://example.test/map.png'),
          ),
        ),
      ),
    );

    final image = tester.widget<CachedNetworkImage>(find.byType(CachedNetworkImage));
    expect(image.imageUrl, 'https://example.test/map.png');
  });
}
