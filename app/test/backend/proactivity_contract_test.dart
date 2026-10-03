import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/proactivity.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';

void main() {
  final fixture =
      jsonDecode(File('../contracts/parity/proactivity_v2.json').readAsStringSync()) as Map<String, dynamic>;

  test('shared feed accepts future producer and UTC identity', () {
    final feed = GeneratedProactivityFeedResponse.fromJson(fixture['feed'] as Map<String, dynamic>);
    expect(feed.items.single.producer, 'future_registered_producer');
    expect(feed.items.single.target.id, 'synthetic-task');
    expect(DateTime.parse(feed.items.single.createdAt).toUtc(), DateTime.utc(2026, 10, 3, 12));
    final outcome = GeneratedProactivityOutcomeResponse.fromJson(fixture['outcome'] as Map<String, dynamic>);
    expect(outcome.acted24h, isTrue);
  });

  test('null required feed fields are rejected', () {
    final feed = Map<String, dynamic>.from(fixture['feed'] as Map<String, dynamic>);
    feed['items'] = null;
    expect(() => GeneratedProactivityFeedResponse.fromJson(feed), throwsFormatException);
  });

  test('transport failures stay distinct from disabled feed', () async {
    final api = ProactivityApi(baseUrl: 'http://localhost/', send: (_) async => http.Response('{}', 503));
    final response = await api.feed();
    expect(response, isA<ApiFailure<GeneratedProactivityFeedResponse>>());
  });
}
