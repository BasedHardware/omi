import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversation_map_page.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/widgets/omi_map_preview.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/scenarios/search.dart' show AuditSearchSource;

/// Renders a synthetic map as the Dart owner would, without the network: a real temporary PNG under the
/// same name pattern, deleted when the fetch is no longer current.
Future<String?> _fixtureMap({
  required List<OmiMapPin> pins,
  required int width,
  required int height,
  required Brightness brightness,
  required bool Function() current,
}) async {
  final recorder = ui.PictureRecorder();
  Canvas(recorder).drawRect(Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
      Paint()..color = brightness == Brightness.dark ? Colors.black : Colors.white);
  final image = await recorder.endRecording().toImage(width, height);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  final directory = await getTemporaryDirectory();
  final file = File('${directory.path}/omi_native_map_host_${DateTime.now().microsecondsSinceEpoch}.png');
  await file.writeAsBytes(data!.buffer.asUint8List(), flush: true);
  if (!current()) {
    await file.delete();
    return null;
  }
  return Uri.file(file.path).toString();
}

ServerConversation _conversation(String id, double latitude, double longitude) => ServerConversation(
      id: id,
      createdAt: DateTime(2026, 10, 4, 10),
      status: ConversationStatus.completed,
      structured: Structured('Place $id', 'A synthetic conversation at a place.'),
      geolocation: Geolocation(latitude: latitude, longitude: longitude),
    );

Widget _app(Widget home) => nativeHostApp(home, providers: [
      ChangeNotifierProvider<ConversationDetailProvider>(
          create: (_) => ConversationDetailProvider(fetchConversation: (_) async => null)),
    ]);

/// Bounded frames for a route or sheet transition; the live binding never settles behind a spinner.
Future<void> _frames(WidgetTester tester) async {
  for (var frame = 0; frame < 10; frame++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
}

/// Waits for real file I/O, then answers whether [uri]'s file still exists.
Future<bool> _exists(WidgetTester tester, String uri) async {
  await tester.pump();
  await Future<void>.delayed(const Duration(milliseconds: 500));
  return File.fromUri(Uri.parse(uri)).exists();
}

/// The Places map, cluster chooser and recap journey on Simulator, with OMI_APP_PROFILE=local_dev and
/// OMI_IOS_SWIFTUI=true.
void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('search Places opens the native conversation map', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        await tester.pumpWidget(nativeHostApp(const GlobalSearchPage(source: AuditSearchSource())));
        await checkNativeHost(tester, 'native-maps-recap-search-dark');
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'search_places').action!(null)));
        await _frames(tester);
        expect(find.byType(ConversationMapPage), findsOneWidget);
        await checkNativeHost(tester, 'native-maps-recap-places-dark');
        expect(tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).title, 'Conversation Map');
        await tester.pumpWidget(const SizedBox());
        expect(tester.takeException(), isNull);
      });

      testWidgets('a single place opens the native conversation detail and the map file is removed', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        await tester.pumpWidget(_app(ConversationMapPage(
            conversations: [_conversation('single', 37.7749, -122.4194)], staticMapResolver: _fixtureMap)));
        await checkNativeHost(tester, 'native-maps-recap-map-dark');
        final uri = nativeProjectedRow(tester, 'conversation_map_image').imageUri!;
        expect(await _exists(tester, uri), isTrue);
        expect(nativeProjectedRow(tester, 'conversation_map_group_0').title, 'Place single');
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'conversation_map_group_0').action!(null)));
        await _frames(tester);
        expect(find.byType(ConversationDetailPage), findsOneWidget);
        await checkNativeHost(tester, 'native-maps-recap-detail-dark');
        await tester.pumpWidget(const SizedBox());
        expect(await _exists(tester, uri), isFalse);
        expect(tester.takeException(), isNull);
      });

      testWidgets('a shared place opens the native chooser, which closes and then opens the detail', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        await tester.pumpWidget(_app(ConversationMapPage(conversations: [
          _conversation('first', 37.77491, -122.41941),
          _conversation('second', 37.77494, -122.41944),
        ], staticMapResolver: _fixtureMap)));
        await checkNativeHost(tester, 'native-maps-recap-cluster-map-dark');
        expect(nativeProjectedRow(tester, 'conversation_map_group_0').title, '2 conversations');
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'conversation_map_group_0').action!(null)));
        await _frames(tester);
        expect(find.byType(ConversationMapClusterChooser), findsOneWidget);
        await tester.pump(const Duration(seconds: 2));
        expect(await captureNativeHostScreenshot('native-maps-recap-chooser-dark'), isNotEmpty);
        expect(nativeProjectedRow(tester, 'conversation_map_cluster_1').title, 'Place second');
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'conversation_map_cluster_1').action!(null)));
        await _frames(tester);
        expect(find.byType(ConversationMapClusterChooser), findsNothing);
        expect(find.byType(ConversationDetailPage), findsOneWidget);
        await checkNativeHost(tester, 'native-maps-recap-chooser-detail-dark');
        await tester.pumpWidget(const SizedBox());
        expect(tester.takeException(), isNull);
      });

      testWidgets('a recap with locations opens the native journey sheet, whose map file is gone after close',
          (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final summary = DailySummary(
          id: 'host-recap',
          date: '2026-10-04',
          createdAt: DateTime(2026, 10, 5),
          headline: 'Around the city',
          overview: 'A synthetic day with two stops.',
          stats: DayStats(totalConversations: 2, totalDurationMinutes: 45),
          locations: [
            LocationPin(latitude: 37.7749, longitude: -122.4194, address: 'Home, San Francisco', time: '08:00'),
            LocationPin(latitude: 37.7849, longitude: -122.4094, address: 'Office, San Francisco', time: '10:00'),
          ],
        );
        final launched = <(double, double)>[];
        await tester.pumpWidget(_app(DailySummaryDetailPage(
          summaryId: summary.id,
          summary: summary,
          staticMapResolver: _fixtureMap,
          launchMap: (latitude, longitude) => launched.add((latitude, longitude)),
        )));
        await checkNativeHost(tester, 'native-maps-recap-summary-dark');
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'recap_locations_map').action!(null)));
        await _frames(tester);
        expect(find.byType(RecapJourneySheet), findsOneWidget);
        await tester.pump(const Duration(seconds: 2));
        expect(await captureNativeHostScreenshot('native-maps-recap-journey-dark'), isNotEmpty);
        final uri = nativeProjectedRow(tester, 'recap_journey_image').imageUri!;
        expect(await _exists(tester, uri), isTrue);
        expect(nativeProjectedRow(tester, 'recap_location_1').title, 'Office');
        await nativeProjectedRow(tester, 'recap_location_1').action!(null);
        expect(launched, [(37.7849, -122.4094)]);
        await nativeProjectedRow(tester, 'recap_journey_close').action!(null);
        await _frames(tester);
        expect(find.byType(RecapJourneySheet), findsNothing);
        expect(await _exists(tester, uri), isFalse);
        await tester.pumpWidget(const SizedBox());
        expect(tester.takeException(), isNull);
      });
    });
