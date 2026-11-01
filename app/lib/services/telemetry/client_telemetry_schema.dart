import 'dart:convert';

/// Frozen client-telemetry schema helpers (transport contract v1).
///
/// Attributes are exhaustive per family. Unknown keys are never added.
class ClientTelemetrySchema {
  ClientTelemetrySchema._();

  static const schemaVersion = 1;
  static const maxObservationsPerBatch = 100;
  static const maxRequestBytes = 128 * 1024;
  static const maxObservationBytes = 4 * 1024;
  static const maxOutboxObservations = 1000;
  static const maxOutboxBytes = 1024 * 1024;
  static const maxOutboxAge = Duration(hours: 24);
  static const maxFutureSkew = Duration(minutes: 5);
  static const maxAttempts = 5;
  static const requestTimeout = Duration(seconds: 10);
  static const flushInterval = Duration(seconds: 30);
  static const retryDelayCapsMs = <int>[2000, 4000, 8000, 16000];
  static const maxRetryAfter = Duration(seconds: 300);
  static const maxLatencyMs = 86400000;
  static const maxSessionDurationMs = 604800000;
  static const histogramBoundsSeconds = <double>[
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2,
    5,
    10,
    30,
    60,
    120,
    300,
    900,
    3600,
    86400,
  ];

  static final uuidPattern = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
  );

  static const platforms = {'ios', 'android', 'macos'};
  static const channels = {'production', 'beta'};
  static const uploadPhases = {'started', 'accepted', 'completed', 'failed', 'deferred'};
  static const uploadSources = {'pendant', 'phone', 'sdcard', 'other', 'unknown'};
  static const failureClasses = {
    'network',
    'timeout',
    'auth',
    'rate_limited',
    'client_error',
    'server_error',
    'cancelled',
    'unknown',
  };
  static const processingOutcomes = {'completed', 'failed', 'cancelled'};
  static const latencyBases = {'processing_observed', 'request_started', 'unknown'};

  /// Native OmiCaptureHealth phases (OmiCaptureHealth.swift) in wire form, plus
  /// the legacy names other emitters may still send. The native set is
  /// inactive, unverified, flowing, repairing, reconnecting, quiet,
  /// actionRequired; `mapIngressPhase` translates each camelCase name.
  static const ingressPhases = {
    'unknown',
    'inactive',
    'unverified',
    'subscribing',
    'awaiting_audio',
    'flowing',
    'quiet',
    'repairing',
    'recovering',
    'reconnecting',
    'action_required',
    'disconnected',
  };
  static const ingressReasons = {
    'none',
    'cccd_timeout_recovery',
    'subscription_timeout',
    'no_audio',
    'stale_audio',
    'disconnected',
    'unauthorized',
    'unknown',
  };
  static const recoveryOutcomes = {'none', 'attempted', 'recovered', 'failed', 'exhausted', 'unknown'};
  static const wedgePhases = {'detected', 'resolved'};
  static const wedgeTriggers = {
    'zero_bytes',
    'rapid_reconnect',
    'bytes_sent_no_transcript',
    'upload_silence',
    'ingress_recovery_failed',
    'other',
    'unknown',
  };
  static const wedgeOutcomes = {'pending', 'recovered', 'failed', 'exhausted', 'unknown'};
  static const vendors = {'omi', 'limitless', 'other', 'unknown'};
  static const disconnectClasses = {'intentional', 'link_loss', 'timeout', 'adapter_off', 'permission', 'unknown'};
  static const requestOrigins = {'explicit_user', 'automatic_roll', 'unknown'};

  static bool isUuid(String value) => uuidPattern.hasMatch(value);

  static String utcIso(DateTime time) {
    final utc = time.toUtc();
    final trimmed = DateTime.utc(
      utc.year,
      utc.month,
      utc.day,
      utc.hour,
      utc.minute,
      utc.second,
      utc.millisecond,
    );
    return trimmed.toIso8601String();
  }

  static String canonicalJson(Object? value) {
    if (value is Map) {
      final keys = value.keys.map((key) => key.toString()).toList()..sort();
      return '{${keys.map((key) => '${jsonEncode(key)}:${canonicalJson(value[key])}').join(',')}}';
    }
    if (value is List) {
      return '[${value.map(canonicalJson).join(',')}]';
    }
    return jsonEncode(value);
  }

  static int utf8Length(String value) => utf8.encode(value).length;

  static String? boundedLatency(int? latencyMs, {int max = maxLatencyMs}) {
    if (latencyMs == null || latencyMs < 0 || latencyMs > max) return null;
    return 'ok';
  }

  static Map<String, Object?> uploadAttributes({
    required String attemptId,
    required String phase,
    required String source,
    int? httpStatus,
    String? failureClass,
    int? latencyMs,
    String? operationId,
  }) {
    return {
      'attempt_id': attemptId,
      'phase': phase,
      'source': uploadSources.contains(source) ? source : 'unknown',
      if (httpStatus != null && httpStatus >= 0) 'http_status': httpStatus,
      if (failureClass != null && failureClasses.contains(failureClass)) 'failure_class': failureClass,
      if (latencyMs != null && latencyMs >= 0 && latencyMs <= maxLatencyMs) 'latency_ms': latencyMs,
      if (operationId != null) 'operation_id': operationId,
    };
  }

  static String mapLegacyUploadFailure(String? legacy, {int? httpStatus}) {
    if (httpStatus != null &&
        httpStatus >= 400 &&
        httpStatus < 500 &&
        httpStatus != 401 &&
        httpStatus != 403 &&
        httpStatus != 408 &&
        httpStatus != 429) {
      return 'client_error';
    }
    return switch (legacy) {
      'network' => 'network',
      'timeout' => 'timeout',
      'authentication' || 'auth' => 'auth',
      'rate_limited' => 'rate_limited',
      'server' || 'server_error' => 'server_error',
      'cancelled' || 'canceled' => 'cancelled',
      'client_error' => 'client_error',
      _ => 'unknown',
    };
  }

  static String mapIngressPhase(String phase) => switch (phase) {
        'actionRequired' => 'action_required',
        'inactive' || 'unverified' || 'flowing' || 'quiet' || 'repairing' || 'reconnecting' => phase,
        _ => ingressPhases.contains(phase) ? phase : 'unknown',
      };

  static bool ingressPhaseMapped(String phase) => mapIngressPhase(phase) != 'unknown';

  static String mapIngressReason(String reason) => ingressReasons.contains(reason) ? reason : 'unknown';

  static String mapRecoveryOutcome(String outcome) => recoveryOutcomes.contains(outcome) ? outcome : 'unknown';

  static String mapWedgeTrigger(String trigger) => switch (trigger) {
        'zero_bytes' || 'zero_byte_streak' => 'zero_bytes',
        'rapid_reconnect' || 'rapid_reconnects' => 'rapid_reconnect',
        'bytes_sent_no_transcript' => 'bytes_sent_no_transcript',
        'upload_silence' => 'upload_silence',
        'ingress_recovery_failed' => 'ingress_recovery_failed',
        'other' => 'other',
        'unknown' => 'unknown',
        _ => 'other',
      };

  static String mapVendor(String analyticsVendor) => switch (analyticsVendor) {
        'omi' => 'omi',
        'limitless' => 'limitless',
        'unknown' || '' => 'unknown',
        _ => 'other',
      };

  static String mapDisconnectClass(String? reason, {bool intentional = false}) {
    if (intentional) return 'intentional';
    return switch (reason) {
      'clean_disconnect' || 'manual' || 'app_closed' => 'intentional',
      'connection_timeout' => 'timeout',
      'remote_device_terminated' || 'link_key_mismatch' || 'pairing_lost' => 'link_loss',
      'adapter_off' => 'adapter_off',
      'permission' || 'permission_denied' => 'permission',
      _ => 'unknown',
    };
  }

  static String mapRequestOrigin(String? origin) => requestOrigins.contains(origin) ? origin! : 'unknown';

  /// Client-visible processing outcome. Null means the row disappeared or is
  /// still unresolved, and must not become a completion.
  static String? processingOutcome({
    required bool lifecycleOk,
    String? lifecycleStatus,
    String? pageStatus,
  }) {
    if (lifecycleOk && lifecycleStatus == 'completed') return 'completed';
    if (lifecycleOk && lifecycleStatus == 'failed') return 'failed';
    if (lifecycleOk && (lifecycleStatus == 'cancelled' || lifecycleStatus == 'canceled')) return 'cancelled';
    if (!lifecycleOk || lifecycleStatus == null) {
      if (pageStatus == 'completed') return 'completed';
      if (pageStatus == 'failed') return 'failed';
      if (pageStatus == 'cancelled' || pageStatus == 'canceled') return 'cancelled';
    }
    return null;
  }

  static List<Map<String, Object>> histogramBuckets(Iterable<int> latencyMs, {bool session = false}) {
    final seconds = <double>[
      for (final ms in latencyMs)
        if (ms >= 0) ms / 1000.0,
    ];
    final bounds = <double>[...histogramBoundsSeconds, if (session) 604800];
    final buckets = <Map<String, Object>>[];
    for (final bound in bounds) {
      buckets.add({
        'le_seconds': bound,
        'count': seconds.where((value) => value <= bound).length,
      });
    }
    buckets.add({
      // contract §7: the wire format is "+Inf" (backend/backend fixtures);
      // the old fixture helper emitted "inf".
      'le_seconds': '+Inf',
      'count': seconds.length,
    });
    return buckets;
  }
}

class ClientTelemetryObservation {
  ClientTelemetryObservation({
    required this.ownerId,
    required this.eventId,
    required this.occurredAt,
    required this.platform,
    required this.channel,
    required this.family,
    required this.attributes,
    required this.enqueuedAt,
    this.attempts = 0,
    this.notBefore,
  });

  final String ownerId;
  final String eventId;
  final DateTime occurredAt;
  final String platform;
  final String channel;
  final String family;
  final Map<String, Object?> attributes;
  final DateTime enqueuedAt;
  int attempts;
  DateTime? notBefore;

  String get wire => ClientTelemetrySchema.canonicalJson({
        'event_id': eventId,
        'occurred_at': ClientTelemetrySchema.utcIso(occurredAt),
        'platform': platform,
        'channel': channel,
        'family': family,
        'attributes': attributes,
      });

  int get wireBytes => ClientTelemetrySchema.utf8Length(wire);

  Map<String, Object?> toJson() => {
        'owner_id': ownerId,
        'event_id': eventId,
        'occurred_at': occurredAt.toUtc().toIso8601String(),
        'platform': platform,
        'channel': channel,
        'family': family,
        'attributes': attributes,
        'enqueued_at': enqueuedAt.toUtc().toIso8601String(),
        'attempts': attempts,
        if (notBefore != null) 'not_before': notBefore!.toUtc().toIso8601String(),
      };

  static ClientTelemetryObservation? fromJson(Map<String, Object?> json) {
    try {
      final attributes = <String, Object?>{};
      final rawAttributes = json['attributes'];
      if (rawAttributes is Map) {
        rawAttributes.forEach((key, value) => attributes[key.toString()] = value);
      }
      return ClientTelemetryObservation(
        ownerId: json['owner_id'] as String,
        eventId: json['event_id'] as String,
        occurredAt: DateTime.parse(json['occurred_at'] as String).toUtc(),
        platform: json['platform'] as String,
        channel: json['channel'] as String,
        family: json['family'] as String,
        attributes: attributes,
        enqueuedAt: DateTime.parse(json['enqueued_at'] as String).toUtc(),
        attempts: json['attempts'] as int? ?? 0,
        notBefore: json['not_before'] == null ? null : DateTime.parse(json['not_before'] as String).toUtc(),
      );
    } catch (_) {
      return null;
    }
  }
}
