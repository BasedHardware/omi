import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/imports.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/import_history_page.dart';

/// Transcript-file import: the job list tells Limitless and transcript imports
/// apart, and the upload URL carries the user's language and IANA timezone.
void main() {
  group('ImportJobResponse.source', () {
    ImportJobResponse job(Map<String, dynamic> extra) =>
        ImportJobResponse.fromJson({'job_id': 'j1', 'status': 'completed', ...extra});

    test('transcript_files jobs are transcript imports', () {
      expect(job({'source_type': 'transcript_files'}).source, ImportJobSource.transcriptFiles);
    });

    test('limitless jobs and jobs from before the field existed are Limitless imports', () {
      expect(job({'source_type': 'limitless'}).source, ImportJobSource.limitless);
      expect(job({}).source, ImportJobSource.limitless);
      expect(job({'source_type': null}).source, ImportJobSource.limitless);
    });

    test('an importer this build does not know is labeled as other, not as Limitless', () {
      expect(job({'source_type': 'granola'}).source, ImportJobSource.other);
    });

    test('toGenerated keeps the source, so a transcript job never round-trips as a Limitless one', () {
      expect(job({'source_type': 'transcript_files'}).toGenerated().sourceType, 'transcript_files');
      expect(job({'source_type': 'limitless'}).toGenerated().sourceType, 'limitless');
      for (final source in ImportJobSource.values) {
        final original = ImportJobResponse(jobId: 'j1', status: ImportJobStatus.completed, source: source);
        expect(ImportJobResponse.fromGenerated(original.toGenerated()).source, source, reason: source.name);
      }
    });
  });

  group('transcriptImportUrl', () {
    test('encodes language, timezone and origin as query parameters', () {
      final url = Uri.parse(
        transcriptImportUrl('https://api.omi.me/', language: 'pt-BR', timeZone: 'America/Sao_Paulo', origin: 'plaud'),
      );

      expect(url.path, '/v1/import/transcripts');
      expect(url.queryParameters, {'language': 'pt-BR', 'tz': 'America/Sao_Paulo', 'origin': 'plaud'});
    });

    test('falls back to English, UTC and an unspecified origin', () {
      final url = Uri.parse(transcriptImportUrl('https://api.omi.me/', language: '', timeZone: null));

      expect(url.queryParameters, {'language': 'en', 'tz': 'UTC', 'origin': 'other'});
    });
  });

  group('importStartFailureMessage', () {
    final l10n = lookupAppLocalizations(const Locale('en'));
    String message(int? status, [String? detail]) =>
        importStartFailureMessage(l10n, ImportStartResult.failed(statusCode: status, errorDetail: detail));

    test('a rate-limited import says to try again later, in the user\'s language', () {
      expect(message(429, 'Rate limit exceeded. Try again in 3540s.'), l10n.importTooManyAttempts);
    });

    test('a file over a size limit says it is too large', () {
      expect(importStartFailureMessage(l10n, const ImportStartResult.tooLarge()), l10n.importFileTooLarge);
      expect(message(413), l10n.importFileTooLarge);
    });

    test('other refusals show the server reason, and fall back to the generic copy', () {
      expect(message(400, 'Upload a .zip, .srt, .vtt or .txt file'), 'Upload a .zip, .srt, .vtt or .txt file');
      expect(message(400), l10n.failedToStartImport);
      expect(message(503, 'The import could not be started. Try again shortly.'), l10n.failedToStartImport);
      expect(message(null), l10n.failedToStartImport);
    });
  });

  group('startTranscriptImport', () {
    test('a file over the upload limit is refused before anything is sent', () async {
      final dir = await Directory.systemTemp.createTemp('omi_import_test');
      addTearDown(() => dir.delete(recursive: true));
      final file = File('${dir.path}/export.zip')..writeAsBytesSync(List.filled(5, 0));

      // No API base URL or network in tests: reaching the request would fail, not report too large.
      final result = await startTranscriptImport(file, maxUploadBytes: 4);

      expect(result.tooLarge, isTrue);
      expect((result.job, result.statusCode), (null, null));
    });
  });

  group('ImportStartResult', () {
    test('a started import carries its job and no failure', () {
      final job = ImportJobResponse(jobId: 'j1', status: ImportJobStatus.pending);
      final result = ImportStartResult.started(job);

      expect(result.job, same(job));
      expect(result.statusCode, isNull);
      expect(result.errorDetail, isNull);
    });

    test('a refused import carries the status and the server reason', () {
      const result = ImportStartResult.failed(statusCode: 429, errorDetail: 'Rate limit exceeded.');

      expect(result.job, isNull);
      expect((result.statusCode, result.errorDetail), (429, 'Rate limit exceeded.'));
    });
  });

  test('the transcript picker accepts exactly the formats the server imports', () {
    expect(transcriptImportExtensions, ['zip', 'srt', 'vtt', 'txt']);
  });

  test('import history shows the Limitless logo only on Limitless jobs', () {
    expect(importJobSourceIcon(ImportJobSource.limitless), isNull);
    expect(importJobSourceIcon(ImportJobSource.transcriptFiles), Icons.subtitles_outlined);
    expect(importJobSourceIcon(ImportJobSource.other), Icons.upload_file_outlined);
  });
}
