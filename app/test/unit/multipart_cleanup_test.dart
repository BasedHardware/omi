import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  final client = _FailingHttpClient();

  setUpAll(() {
    Env.init(_TestEnv());
    PlatformManager.initializeForLocalHarness();
    HttpOverrides.runWithHttpOverrides(() => HttpPoolManager.instance, _HttpOverrides(client));
  });

  setUp(() {
    client.beforeFailure = null;
    client.requests = 0;
  });

  tearDownAll(() => HttpPoolManager.instance.dispose());

  test('handled multipart connection failure does not also escape to the zone', () async {
    final uncaught = await _captureUncaught(() async {
      await expectLater(
        makeMultipartApiCall(url: 'https://upload.invalid/audio', files: const [], onUploadProgress: (_, __, ___) {}),
        throwsA(isA<SocketException>().having((error) => error.message, 'message', 'Connection refused')),
      );
    });

    expect(client.requests, 1);
    expect(uncaught, isEmpty);
  });

  test('failed multipart upload awaits cancellation of its active file stream', () async {
    final file = _PendingFile();
    client.beforeFailure = file.started.future;
    var callerCompleted = false;

    final uncaught = await _captureUncaught(() async {
      final upload = makeMultipartApiCall(
        url: 'https://upload.invalid/audio',
        files: [file],
        onUploadProgress: (_, __, ___) {},
      );
      final handled = expectLater(
        upload,
        throwsA(isA<SocketException>().having((error) => error.message, 'message', 'Connection refused')),
      ).then((_) => callerCompleted = true);

      await file.cancelling.future;
      try {
        // Flush queued completion callbacks without a timer delay. Cleanup must
        // finish before the failed request is delivered to its caller.
        await Future<void>(() {});
        expect(callerCompleted, isFalse);
      } finally {
        file.allowCancellation.complete();
      }
      await handled;
      expect(file.cancelled, isTrue);
    });

    expect(client.requests, 1);
    expect(callerCompleted, isTrue);
    expect(uncaught, isEmpty);
  });
}

Future<List<Object>> _captureUncaught(Future<void> Function() body) async {
  final uncaught = <Object>[];
  final completed = Completer<void>();
  runZonedGuarded(() async {
    try {
      await body();
      completed.complete();
    } catch (error, stackTrace) {
      completed.completeError(error, stackTrace);
    }
  }, (error, _) => uncaught.add(error));
  await completed.future;
  await Future<void>(() {});
  return uncaught;
}

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://auth-not-required.invalid/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _HttpOverrides extends HttpOverrides {
  _HttpOverrides(this.client);

  final HttpClient client;

  @override
  HttpClient createHttpClient(SecurityContext? context) => client;
}

class _FailingHttpClient implements HttpClient {
  Future<void>? beforeFailure;
  int requests = 0;

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    requests++;
    await beforeFailure;
    throw const SocketException('Connection refused');
  }

  @override
  int? maxConnectionsPerHost;

  @override
  Duration idleTimeout = const Duration(seconds: 15);

  @override
  void close({bool force = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('Unexpected HttpClient call: ${invocation.memberName}');
}

/// Keeps the multipart body open until the failed send cancels it. No file or
/// network IO is needed to exercise the production upload/progress path.
class _PendingFile implements File {
  final started = Completer<void>();
  final cancelling = Completer<void>();
  final allowCancellation = Completer<void>();
  bool cancelled = false;

  @override
  String get path => '/synthetic/audio.bin';

  @override
  Future<int> length() async => 1;

  @override
  Stream<List<int>> openRead([int? start, int? end]) {
    return StreamController<List<int>>(
      onListen: started.complete,
      onCancel: () async {
        cancelling.complete();
        await allowCancellation.future;
        cancelled = true;
      },
    ).stream;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('Unexpected File call: ${invocation.memberName}');
}
