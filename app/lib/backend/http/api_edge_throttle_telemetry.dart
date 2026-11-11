import 'package:http/http.dart' as http;
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Bounded, process-local telemetry. Templates come only from this allowlist;
/// unknown paths collapse to /other rather than guessing which segments are IDs.
class ApiEdgeThrottleTelemetry {
  ApiEdgeThrottleTelemetry({
    required this.emit,
    required this.elapsedMilliseconds,
  });

  static final _clock = Stopwatch()..start();
  static final instance = ApiEdgeThrottleTelemetry(
    emit: (name, properties) => AnalyticsManager().track(name, properties: properties),
    elapsedMilliseconds: () => _clock.elapsedMilliseconds,
  );

  final void Function(String, Map<String, dynamic>) emit;
  final int Function() elapsedMilliseconds;
  final Map<String, int> _lastSent = {};
  static const _intervalMs = 5 * 60 * 1000;

  // Specific routes precede collection/record templates. No captured URL value
  // is transmitted; even all-letter IDs and percent-encoded text are discarded.
  static final _templates = <String>[
    '/v2/sync-local-files/{id}',
    '/v2/sync-local-files',
    '/v1/sync-local-files/{id}',
    '/v1/sync-local-files',
    '/v1/conversations/from-segments',
    '/v1/conversations/{id}/reprocess',
    '/v1/conversations/{id}/photos',
    '/v1/conversations/{id}',
    '/v1/conversations',
    '/v3/conversations/{id}',
    '/v3/conversations',
    '/v1/action-items/{id}',
    '/v1/action-items',
    '/v3/memories/{id}',
    '/v3/memories',
    '/v2/messages',
    '/v1/messages',
    '/v1/users/me',
    '/v1/fair-use',
    '/v4/listen',
  ];
  static final _patterns = {
    for (final template in _templates)
      template: RegExp('^${RegExp.escape(template).replaceAll(r'\{id\}', r'[^/]+')}/?\$'),
  };

  static String endpointTemplate(Uri uri) {
    for (final entry in _patterns.entries) {
      if (entry.value.hasMatch(uri.path)) return entry.key;
    }
    return '/other';
  }

  void observe(http.BaseRequest request, http.BaseResponse response) {
    final uri = request.url;
    if (response.statusCode != 429 ||
        uri.scheme != 'https' ||
        !const {'api.omi.me', 'api.omiapi.com'}.contains(uri.host)) {
      return;
    }

    final endpoint = endpointTemplate(uri);
    final now = elapsedMilliseconds();
    final previous = _lastSent[endpoint];
    // Deliberately shared across methods: <=1 event per template per 5 min.
    if (previous != null && now - previous < _intervalMs) return;
    _lastSent[endpoint] = now;
    final method = request.method.toUpperCase();
    final properties = <String, dynamic>{
      'endpoint_template': endpoint,
      'method': const {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}.contains(method) ? method : 'OTHER',
      'path_family': endpoint.contains('sync-local-files')
          ? 'sync'
          : endpoint == '/v4/listen'
              ? 'listen'
              : 'api',
      'trigger': 'system',
    };
    String? retryAfter;
    for (final header in response.headers.entries) {
      if (header.key.toLowerCase() == 'retry-after') retryAfter = header.value.trim();
    }
    // Accept only protocol-valid delay/date values, never arbitrary header text.
    if (retryAfter != null) {
      if (RegExp(r'^\d{1,10}$').hasMatch(retryAfter) ||
          RegExp(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$')
              .hasMatch(retryAfter)) {
        properties['retry_after'] = retryAfter;
      }
    }
    try {
      emit('api_edge_throttled', properties);
    } catch (_) {
      // Analytics must never change the API response or create an HTTP retry.
    }
  }
}
