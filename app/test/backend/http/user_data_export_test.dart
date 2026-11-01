import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/user_data_export.dart';

const _suffix = ',\n  "export_complete": true\n}\n';

http.StreamedResponse _response(
  Stream<List<int>> stream, {
  int statusCode = 200,
  Map<String, String> headers = const {'content-type': 'application/json'},
  int? contentLength,
}) {
  return http.StreamedResponse(stream, statusCode, headers: headers, contentLength: contentLength);
}

Stream<List<int>> _chunks(List<String> parts) => Stream.fromIterable(parts.map(utf8.encode));

Stream<List<int>> _failingStream() async* {
  yield utf8.encode('{\n  "conversations": [\n');
  throw StateError('socket reset');
}

void main() {
  late Directory tempDir;
  late String filePath;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('export-test');
    filePath = '${tempDir.path}/omi-export.json';
  });

  tearDown(() async {
    if (await tempDir.exists()) await tempDir.delete(recursive: true);
  });

  Future<void> expectNoPartialFiles() async {
    final partials = await tempDir
        .list()
        .where((entity) => entity.path.startsWith('$filePath.') && entity.path.endsWith('.part'))
        .toList();
    expect(partials, isEmpty);
  }

  test('writes a complete export and reports cumulative progress', () async {
    const body = '{\n  "chat_messages": [\n\n  ]\n$_suffix';

    const splitAt = body.length - _suffix.length + 5;
    final progress = <int>[];

    final result = await exportUserDataToFile(
      filePath,
      onProgress: progress.add,
      request: () async =>
          _response(_chunks([body.substring(0, splitAt), body.substring(splitAt)]), contentLength: body.length),
    );

    expect(result, filePath);
    expect(await File(filePath).readAsString(), body);
    expect(progress, [splitAt, body.length]);
  });

  test('returns null and deletes the partial file on HTTP error', () async {
    final result = await exportUserDataToFile(
      filePath,
      request: () async => _response(_chunks(['']), statusCode: 504, headers: {}),
    );

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null on a non-JSON content type', () async {
    final result = await exportUserDataToFile(
      filePath,
      request: () async => _response(_chunks(['{}$_suffix']), headers: {'content-type': 'text/html'}),
    );

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null when Content-Length does not match received bytes', () async {
    const body = '{\n}$_suffix';
    final result = await exportUserDataToFile(
      filePath,
      request: () async => _response(_chunks([body]), contentLength: body.length + 10),
    );

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null on a silently truncated 200 without the marker', () async {
    final result = await exportUserDataToFile(
      filePath,
      request: () async => _response(_chunks(['{\n  "profile": {},\n  "chat_m'])),
    );

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null when the stream fails mid-body', () async {
    final result = await exportUserDataToFile(filePath, request: () async => _response(_failingStream()));

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null on an empty body', () async {
    final result = await exportUserDataToFile(filePath, request: () async => _response(_chunks([])));

    expect(result, isNull);
    await expectNoPartialFiles();
  });

  test('returns null when the stream stalls past the idle timeout', () async {
    final controller = StreamController<List<int>>();
    final result = await exportUserDataToFile(
      filePath,
      idleTimeout: const Duration(milliseconds: 100),
      request: () async {
        controller.add(utf8.encode('{\n  "profile": '));
        return _response(controller.stream);
      },
    );

    expect(result, isNull);
    await expectNoPartialFiles();
    await controller.close();
  });

  test('abortTrigger cancels the download and returns null', () async {
    final abort = Completer<void>();
    final controller = StreamController<List<int>>();
    final progress = <int>[];

    final pending = exportUserDataToFile(
      filePath,
      abortTrigger: abort.future,
      onProgress: progress.add,
      request: () async => _response(controller.stream),
    );
    controller.add(utf8.encode('{\n  "profile": '));
    await Future<void>.delayed(Duration.zero);
    abort.complete();

    expect(await pending, isNull);
    await expectNoPartialFiles();
    await controller.close();
  });

  test('a failed export preserves a pre-existing destination file', () async {
    await File(filePath).writeAsString('previous export');

    final result = await exportUserDataToFile(
      filePath,
      request: () async => _response(_chunks(['{"partial": "no marker'])),
    );

    expect(result, isNull);
    expect(await File(filePath).readAsString(), 'previous export');
  });

  test('a successful export replaces the destination atomically', () async {
    await File(filePath).writeAsString('previous export');
    const body = '{\n}$_suffix';

    final result = await exportUserDataToFile(filePath, request: () async => _response(_chunks([body])));

    expect(result, filePath);
    expect(await File(filePath).readAsString(), body);
  });
}
