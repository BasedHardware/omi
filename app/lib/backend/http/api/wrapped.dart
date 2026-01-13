import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Wrapped status enum
enum WrappedStatus {
  notGenerated,
  processing,
  done,
  error,
}

/// Wrapped 2025 response model
class Wrapped2025Response {
  final WrappedStatus status;
  final int year;
  final Map<String, dynamic>? result;
  final String? error;
  final Map<String, dynamic>? progress;

  Wrapped2025Response({
    required this.status,
    this.year = 2025,
    this.result,
    this.error,
    this.progress,
  });

  factory Wrapped2025Response.fromJson(Map<String, dynamic> json) {
    WrappedStatus status;
    switch (json['status']) {
      case 'done':
        status = WrappedStatus.done;
        break;
      case 'processing':
        status = WrappedStatus.processing;
        break;
      case 'error':
        status = WrappedStatus.error;
        break;
      default:
        status = WrappedStatus.notGenerated;
    }

    return Wrapped2025Response(
      status: status,
      year: json['year'] ?? 2025,
      result: json['result'],
      error: json['error'],
      progress: json['progress'],
    );
  }
}

/// Get wrapped 2025 status and result
Future<Wrapped2025Response?> getWrapped2025() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/wrapped/2025',
    headers: {},
    method: 'GET',
    body: '',
  );

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
    final json = jsonDecode(response.body);
    // The generate endpoint returns {status, message}
    return Wrapped2025Response(
      status: json['status'] == 'done'
          ? WrappedStatus.done
          : json['status'] == 'processing'
              ? WrappedStatus.processing
              : json['status'] == 'error'
                  ? WrappedStatus.error
                  : WrappedStatus.notGenerated,
    );
  }
  return null;
}
