import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/wrapped_task_integrations_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Wrapped status enum
enum WrappedStatus { notGenerated, processing, done, error }

WrappedStatus _wrappedStatusFromWire(String status) {
  switch (status) {
    case 'done':
      return WrappedStatus.done;
    case 'processing':
      return WrappedStatus.processing;
    case 'error':
      return WrappedStatus.error;
    default:
      return WrappedStatus.notGenerated;
  }
}

/// Wrapped 2025 response model
class Wrapped2025Response {
  final WrappedStatus status;
  final int year;
  final Map<String, dynamic>? result;
  final String? error;
  final Map<String, dynamic>? progress;

  Wrapped2025Response({required this.status, this.year = 2025, this.result, this.error, this.progress});

  factory Wrapped2025Response.fromJson(Map<String, dynamic> json) {
    return Wrapped2025Response.fromGenerated(wire.GeneratedWrappedStatusResponse.fromJson(json));
  }

  factory Wrapped2025Response.fromGenerated(wire.GeneratedWrappedStatusResponse generated) {
    return Wrapped2025Response(
      status: _wrappedStatusFromWire(generated.status),
      year: generated.year,
      result: generated.result,
      error: generated.error,
      progress: generated.progress,
    );
  }

  wire.GeneratedWrappedStatusResponse toGenerated() {
    return wire.GeneratedWrappedStatusResponse(
      status: status.name == 'notGenerated' ? 'not_generated' : status.name,
      year: year,
      result: result,
      error: error,
      progress: progress,
    );
  }
}

/// Get wrapped 2025 status and result
Future<Wrapped2025Response?> getWrapped2025() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/wrapped/2025', headers: {}, method: 'GET', body: '');

  if (response == null) return null;
  Logger.debug('getWrapped2025 response: ${response.body}');

  if (response.statusCode == 200) {
    return Wrapped2025Response.fromJson(jsonDecode(response.body));
  }
  return null;
}

/// Start wrapped 2025 generation
Future<Wrapped2025Response?> generateWrapped2025() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/wrapped/2025/generate',
    headers: {},
    method: 'POST',
    body: '',
  );

  if (response == null) return null;
  Logger.debug('generateWrapped2025 response: ${response.body}');

  if (response.statusCode == 200) {
    final generated = wire.GeneratedGenerateWrappedResponse.fromJson(jsonDecode(response.body));
    // The generate endpoint returns {status, message}
    return Wrapped2025Response(status: _wrappedStatusFromWire(generated.status));
  }
  return null;
}
