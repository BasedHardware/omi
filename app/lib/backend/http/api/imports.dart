import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/imports_integrations_wire.g.dart' as wire;
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;
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

/// Which importer created a job. Jobs from before the server reported it were
/// all Limitless imports; an importer this build does not know is [other].
enum ImportJobSource {
  limitless,
  transcriptFiles,
  other;

  static ImportJobSource fromWire(String? value) {
    switch (value) {
      case null:
      case 'limitless':
        return ImportJobSource.limitless;
      case 'transcript_files':
        return ImportJobSource.transcriptFiles;
      default:
        return ImportJobSource.other;
    }
  }
}

/// Import job response model
class ImportJobResponse {
  final String jobId;
  final ImportJobStatus status;
  final ImportJobSource source;
  final int? totalFiles;
  final int? processedFiles;
  final int? conversationsCreated;
  final int? conversationsSkipped;
  final DateTime? createdAt;
  final String? error;

  ImportJobResponse({
    required this.jobId,
    required this.status,
    this.source = ImportJobSource.limitless,
    this.totalFiles,
    this.processedFiles,
    this.conversationsCreated,
    this.conversationsSkipped,
    this.createdAt,
    this.error,
  });

  factory ImportJobResponse.fromJson(Map<String, dynamic> json) {
    return ImportJobResponse.fromGenerated(wire.GeneratedImportJobResponse.fromJson(json));
  }

  factory ImportJobResponse.fromGenerated(wire.GeneratedImportJobResponse generated) {
    return ImportJobResponse(
      jobId: generated.jobId,
      status: ImportJobStatus.fromString(generated.status),
      source: ImportJobSource.fromWire(generated.sourceType),
      totalFiles: generated.totalFiles,
      processedFiles: generated.processedFiles,
      conversationsCreated: generated.conversationsCreated,
      conversationsSkipped: generated.conversationsSkipped,
      createdAt: generated.createdAt == null ? null : DateTime.tryParse(generated.createdAt!),
      error: generated.error,
    );
  }

  /// Generated-backed list parser for top-level array responses (e.g. GET
  /// /v1/import/jobs). Routes the raw JSON through the generated wire DTO so
  /// the inventory gate classifies this decode site as generated-backed.
  static List<ImportJobResponse> fromGeneratedWireJsonList(String body) {
    final data = jsonDecode(body) as List;
    return data
        .map(
          (json) =>
              ImportJobResponse.fromGenerated(wire.GeneratedImportJobResponse.fromJson(json as Map<String, dynamic>)),
        )
        .toList();
  }

  wire.GeneratedImportJobResponse toGenerated() {
    return wire.GeneratedImportJobResponse(
      jobId: jobId,
      status: status.name,
      totalFiles: totalFiles,
      processedFiles: processedFiles,
      conversationsCreated: conversationsCreated,
      conversationsSkipped: conversationsSkipped,
      createdAt: createdAt?.toUtc().toIso8601String(),
      error: error,
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

/// File types the transcript importer accepts: one transcript, or a ZIP of them.
const transcriptImportExtensions = ['zip', 'srt', 'vtt', 'txt'];

String transcriptImportUrl(String baseUrl, {required String language, String? timeZone, String origin = 'other'}) {
  return Uri.parse('${baseUrl}v1/import/transcripts').replace(
    queryParameters: {
      'language': language.isEmpty ? 'en' : language,
      'tz': (timeZone == null || timeZone.isEmpty) ? 'UTC' : timeZone,
      'origin': origin,
    },
  ).toString();
}

/// The outcome of starting an import: the job to poll, or the server's reason for
/// refusing it (its `detail`), when it gave one.
class ImportStartResult {
  const ImportStartResult.started(ImportJobResponse this.job) : errorDetail = null;
  const ImportStartResult.failed({this.errorDetail}) : job = null;

  final ImportJobResponse? job;
  final String? errorDetail;
}

/// The plain-text `detail` of a refused import upload (wrong file type, rate limit,
/// server busy), or null when the body carries none.
String? importStartErrorDetail(String body) {
  try {
    final detail = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).detail;
    return detail is String && detail.trim().isNotEmpty ? detail.trim() : null;
  } catch (_) {
    return null;
  }
}

/// Start importing SRT, VTT or TXT transcripts (or a ZIP of them) exported from
/// other apps. `origin` stays API-only: the app always sends the default.
Future<ImportStartResult> startTranscriptImport(
  File file, {
  String language = 'en',
  String? timeZone,
  String origin = 'other',
}) async {
  try {
    final response = await makeMultipartApiCall(
      url: transcriptImportUrl(Env.apiBaseUrl ?? '', language: language, timeZone: timeZone, origin: origin),
      files: [file],
      fileFieldName: 'file',
    );
    if (response.statusCode == 200) {
      final data = wire.GeneratedImportJobResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      return ImportStartResult.started(ImportJobResponse.fromGenerated(data));
    }
    Logger.debug('Failed to start transcript import. Status: ${response.statusCode}');
    return ImportStartResult.failed(errorDetail: importStartErrorDetail(response.body));
  } catch (e) {
    Logger.debug('Error starting transcript import: $e');
    return const ImportStartResult.failed();
  }
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
      var data = wire.GeneratedImportJobResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      Logger.debug('startLimitlessImport Response: $data');
      return ImportJobResponse.fromGenerated(data);
    } else {
      Logger.debug('Failed to start import. Status: ${response.statusCode}, Body: ${response.body}');
      return null;
    }
  } catch (e) {
    Logger.debug('Error starting Limitless import: $e');
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
      return ImportJobResponse.fromGeneratedWireJsonList(response.body);
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
      final data = wire.GeneratedDeleteLimitlessConversationsResponse.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
      Logger.debug('deleteLimitlessConversations Response: $data');
      return data.deletedCount;
    } else {
      Logger.debug('Failed to delete Limitless conversations. Response: ${response?.body}');
      return null;
    }
  } catch (e) {
    Logger.debug('Error deleting Limitless conversations: $e');
    return null;
  }
}
