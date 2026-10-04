import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/imports.dart';
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

  group('importStartErrorDetail', () {
    test('reads the reason the server gave for refusing the upload', () {
      expect(
        importStartErrorDetail('{"detail": "Upload a .zip, .srt, .vtt or .txt file"}'),
        'Upload a .zip, .srt, .vtt or .txt file',
      );
    });

    test('has no reason for validation lists, blank details or non-JSON bodies', () {
      expect(importStartErrorDetail('{"detail": [{"loc": ["query", "tz"], "msg": "bad"}]}'), isNull);
      expect(importStartErrorDetail('{"detail": "  "}'), isNull);
      expect(importStartErrorDetail('<html>502 Bad Gateway</html>'), isNull);
      expect(importStartErrorDetail(''), isNull);
    });
  });

  group('ImportStartResult', () {
    test('a started import carries its job and no failure reason', () {
      final job = ImportJobResponse(jobId: 'j1', status: ImportJobStatus.pending);
      final result = ImportStartResult.started(job);

      expect(result.job, same(job));
      expect(result.errorDetail, isNull);
    });

    test('a refused import carries the server reason when there was one', () {
      expect(const ImportStartResult.failed(errorDetail: 'Rate limit exceeded.').errorDetail, 'Rate limit exceeded.');
      expect(const ImportStartResult.failed().job, isNull);
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
