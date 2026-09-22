import 'dart:convert';
import 'package:http/http.dart' as http;
import 'experiment_definition.dart';

/// Direct public flags evaluation avoids the native SDK's persistent cache and
/// automatic `$feature_flag_called`. No personal API credentials belong here.
class PosthogExperimentFlagProvider implements ExperimentFlagProvider {
  PosthogExperimentFlagProvider(
      {required this.projectToken,
      required Uri host,
      http.Client? client,
      DateTime Function()? now,
      this.timeout = const Duration(seconds: 2)})
      : _client = client ?? http.Client(),
        _now = now ?? DateTime.now,
        _endpoint = host.replace(path: '/flags/', query: 'v=2', fragment: '') {
    if (host.scheme != 'https' ||
        !const {'us.i.posthog.com', 'eu.i.posthog.com', 'app.posthog.com'}.contains(host.host) ||
        host.userInfo.isNotEmpty ||
        host.hasPort ||
        projectToken.isEmpty) {
      throw ArgumentError('Expected a configured PostHog cloud ingest host and public project token');
    }
  }
  final String projectToken;
  final http.Client _client;
  final Uri _endpoint;
  final DateTime Function() _now;
  final Duration timeout;

  @override
  Future<ExperimentFlagSnapshot> fetch(ExperimentContext context) async {
    if (!context.analyticsEnabled || context.identityKey.isEmpty) throw StateError('Experiment consent unavailable');
    final request = http.Request('POST', _endpoint)
      ..followRedirects = false
      ..headers.addAll({'Content-Type': 'application/json', 'User-Agent': 'posthog-flutter/omi-experiments'})
      ..body = jsonEncode({
        'api_key': projectToken,
        'distinct_id': context.identityKey,
        'person_properties': {'experiment_namespace': context.namespace, 'app_build': context.appBuild}
      });
    final response = await _client.send(request).then(http.Response.fromStream).timeout(timeout);
    if (response.statusCode != 200 || response.bodyBytes.length > 1024 * 1024) {
      throw const FormatException('Flag response unavailable');
    }
    final body = jsonDecode(response.body);
    if (body is! Map ||
        body['flags'] is! Map ||
        body['errorsWhileComputingFlags'] != false ||
        (body['quotaLimited'] is List && (body['quotaLimited'] as List).isNotEmpty)) {
      throw const FormatException('Incomplete flag response');
    }
    final values = <String, Object>{};
    for (final entry in (body['flags'] as Map).entries) {
      final flag = entry.value;
      if (entry.key is! String || flag is! Map || flag['enabled'] is! bool || flag['failed'] == true) continue;
      final value = flag['enabled'] == true ? (flag['variant'] ?? true) : false;
      if (value is bool || value is String) values[entry.key as String] = value;
    }
    return ExperimentFlagSnapshot(values: values, fetchedAt: _now(), identityKey: context.identityKey);
  }

  void close() => _client.close();
}
