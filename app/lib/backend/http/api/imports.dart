import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Import job status enum matching the backend
enum ImportJobStatus {
  pending,
  processing,
  completed,
  failed;

  static ImportJobStatus fromString(String status) {
    switch (status) {
      case 'pending':
        return ImportJobStatus.pending;
      case 'processing':
        return ImportJobStatus.processing;
      case 'completed':
        return ImportJobStatus.completed;
      case 'failed':
        return ImportJobStatus.failed;
      default:
        return ImportJobStatus.pending;
    }
  }
}

/// Import job response model
class ImportJobResponse {
  final String jobId;
  final ImportJobStatus status;
  final int? totalFiles;
  final int? processedFiles;
  final int? conversationsCreated;
  final DateTime? createdAt;
  final String? error;

  ImportJobResponse({
    required this.jobId,
    required this.status,
    this.totalFiles,
    this.processedFiles,
    this.conversationsCreated,
    this.createdAt,
    this.error,
  });

  factory ImportJobResponse.fromJson(Map<String, dynamic> json) {
    return ImportJobResponse(
      jobId: json['job_id'] as String,
      status: ImportJobStatus.fromString(json['status'] as String),
      totalFiles: json['total_files'] as int?,
      processedFiles: json['processed_files'] as int?,
      conversationsCreated: json['conversations_created'] as int?,
      createdAt: json['created_at'] != null ? DateTime.tryParse(json['created_at'] as String) : null,
      error: json['error'] as String?,
    );
  }

  double get progress {
    if (totalFiles == null || totalFiles == 0) return 0;
    return (processedFiles ?? 0) / totalFiles!;
  }

  bool get isCompleted => status == ImportJobStatus.completed;
  bool get isFailed => status == ImportJobStatus.failed;
  bool get isProcessing => status == ImportJobStatus.processing || status == ImportJobStatus.pending;
}

/// Start a Limitless import from a ZIP file
/// Returns the import job response with job_id for status tracking
Future<ImportJobResponse?> startLimitlessImport(File zipFile, {String language = 'en'}) async {
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v1/import/limitless?language=$language',
      files: [zipFile],
      fileFieldName: 'file',
    );

    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      Logger.debug('startLimitlessImport Response: $data');
      return ImportJobResponse.fromJson(data);
    } else {
      Logger.debug('Failed to start import. Status: ${response.statusCode}, Body: ${response.body}');
      return null;
    }
  } catch (e) {
    Logger.debug('Error starting Limitless import: $e');
    return null;
  }
}

/// Get the status of a specific import job
Future<ImportJobResponse?> getImportJobStatus(String jobId) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/import/jobs/$jobId',
      headers: {},
      method: 'GET',
      body: '',
    );

    if (response != null && response.statusCode == 200) {
      var data = jsonDecode(response.body);
      return ImportJobResponse.fromJson(data);
    } else {
      Logger.debug('Failed to get import job status. Response: ${response?.body}');
      return null;
    }
  } catch (e) {
    Logger.debug('Error getting import job status: $e');
    return null;
  }
}

/// Get all import jobs for the current user
Future<List<ImportJobResponse>> getImportJobs({int limit = 50}) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/import/jobs?limit=$limit',
      headers: {},
      method: 'GET',
      body: '',
    );

    if (response != null && response.statusCode == 200) {
      var data = jsonDecode(response.body) as List;
      return data.map((json) => ImportJobResponse.fromJson(json)).toList();
    } else {
      Logger.debug('Failed to get import jobs. Response: ${response?.body}');
      return [];
    }
  } catch (e) {
    Logger.debug('Error getting import jobs: $e');
    return [];
  }
}

/// Delete all Limitless conversations
/// Returns the number of deleted conversations, or null on error
Future<int?> deleteLimitlessConversations() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/import/limitless/conversations',
      headers: {},
      method: 'DELETE',
      body: '',
    );

    if (response != null && response.statusCode == 200) {
      var data = jsonDecode(response.body);
      Logger.debug('deleteLimitlessConversations Response: $data');
      return data['deleted_count'] as int?;
    } else {
      Logger.debug('Failed to delete Limitless conversations. Response: ${response?.body}');
      return null;
    }
  } catch (e) {
    Logger.debug('Error deleting Limitless conversations: $e');
    return null;
  }
}
