import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi/services/experiments/posthog_experiment_flag_provider.dart';
import 'package:omi/services/experiments/experiment_definition.dart';

void main() {
  const context =
      ExperimentContext(identityKey: 'test-identity', analyticsEnabled: true, namespace: 'mobile-test', appBuild: 1000);
  test('public flags request carries current identity and never emits exposure', () async {
    final provider = PosthogExperimentFlagProvider(
        projectToken: 'public-test-token',
        host: Uri.parse('https://us.i.posthog.com'),
        client: MockClient((request) async {
          expect(request.url.path, '/flags/');
          expect(request.url.query, 'v=2');
          expect(request.followRedirects, false);
          expect(jsonDecode(request.body), {
            'api_key': 'public-test-token',
            'distinct_id': 'test-identity',
            'person_properties': {'experiment_namespace': 'mobile-test', 'app_build': 1000}
          });
          return http.Response(
              jsonEncode({
                'errorsWhileComputingFlags': false,
                'flags': {
                  'trial': {'enabled': true, 'variant': 'test'},
                  'switch': {'enabled': false},
                  'malformed': {'enabled': 'yes'},
                  'failed': {'enabled': true, 'failed': true}
                }
              }),
              200);
        }));
    final snapshot = await provider.fetch(context);
    expect(snapshot.values, {'trial': 'test', 'switch': false});
    expect(snapshot.identityKey, context.identityKey);
    expect(snapshot.authoritative, true);
    provider.close();
  });
  test('partial results and quota limits are rejected', () async {
    for (final body in [
      {'flags': {}, 'errorsWhileComputingFlags': true},
      {
        'flags': {},
        'errorsWhileComputingFlags': false,
        'quotaLimited': ['feature_flags']
      },
      {'flags': {}}
    ]) {
      final provider = PosthogExperimentFlagProvider(
          projectToken: 'public-test-token',
          host: Uri.parse('https://eu.i.posthog.com'),
          client: MockClient((_) async => http.Response(jsonEncode(body), 200)));
      await expectLater(provider.fetch(context), throwsFormatException);
      provider.close();
    }
  });
  test('never accepts an unrelated host', () {
    expect(() => PosthogExperimentFlagProvider(projectToken: 'test', host: Uri.parse('https://example.invalid')),
        throwsArgumentError);
  });
}
