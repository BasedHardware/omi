import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/logger.dart';

final List<int> _exportCompletionSuffix = utf8.encode(',\n  "export_complete": true\n}\n');

Future<void> _drainBounded(http.StreamedResponse response) async {
  try {
    await response.stream.drain<void>().timeout(const Duration(seconds: 5));
  } catch (_) {}
}

Future<String?> exportUserDataToFile(
  String filePath, {
  void Function(int bytesReceived)? onProgress,
  Future<void>? abortTrigger,
  Future<http.StreamedResponse> Function()? request,
  Duration idleTimeout = const Duration(minutes: 2),
  AuthSessionSnapshot? authorizationSnapshot,
  AuthService? authService,
}) async {
  final service = authService ?? AuthService.instance;
  var snapshot = authorizationSnapshot;
  if (snapshot == null && request == null) {
    snapshot = service.captureSessionSnapshot();
    if (snapshot == null) {
      Logger.debug('exportUserDataToFile aborted: no authenticated session');
      return null;
    }
  }
  final tempPath = '$filePath.${const Uuid().v4()}.part';
  final tempFile = File(tempPath);
  final abort = Completer<void>();
  if (abortTrigger != null) {
    unawaited(
      abortTrigger.then((_) {
        if (!abort.isCompleted) abort.complete();
      }),
    );
  }
  StreamSubscription<int>? generationWatch;
  if (snapshot != null) {
    generationWatch = service.sessionGenerationEvents.listen((_) {
      if (!service.isSessionSnapshotCurrent(snapshot!) && !abort.isCompleted) {
        abort.complete();
      }
    });
  }
  RandomAccessFile? output;
  var finished = false;
  try {
    final response = await (request ??
        () => makeRawApiCall(
              url: '${Env.apiBaseUrl}v1/users/export?stream=true',
              method: 'GET',
              abortTrigger: abort.future,
              sessionSnapshot: snapshot,
              authService: service,
            ))();
    if (response.statusCode != 200) {
      Logger.debug('exportUserDataToFile failed: HTTP ${response.statusCode}');
      await _drainBounded(response);
      return null;
    }
    final contentType = response.headers['content-type'] ?? '';
    if (contentType.split(';').first.trim().toLowerCase() != 'application/json') {
      Logger.debug('exportUserDataToFile failed: unexpected content-type');
      await _drainBounded(response);
      return null;
    }

    output = await tempFile.open(mode: FileMode.writeOnly);
    var received = 0;
    final tail = <int>[];
    final iterator = StreamIterator(response.stream.timeout(idleTimeout));
    unawaited(abort.future.then((_) => iterator.cancel()).then((_) {}, onError: (_) {}));
    try {
      while (true) {
        final hasNext = await iterator.moveNext();
        if (hasNext != true || abort.isCompleted) break;
        final chunk = iterator.current;
        await output.writeFrom(chunk);
        received += chunk.length;
        if (chunk.length >= _exportCompletionSuffix.length) {
          tail
            ..clear()
            ..addAll(chunk.sublist(chunk.length - _exportCompletionSuffix.length));
        } else {
          tail.addAll(chunk);
          if (tail.length > _exportCompletionSuffix.length) {
            tail.removeRange(0, tail.length - _exportCompletionSuffix.length);
          }
        }
        onProgress?.call(received);
      }
    } finally {
      unawaited(iterator.cancel().then((_) {}, onError: (_) {}));
    }
    if (abort.isCompleted) {
      Logger.debug('exportUserDataToFile aborted');
      return null;
    }

    final declaredLength = response.contentLength;
    if (declaredLength != null && declaredLength >= 0 && declaredLength != received) {
      Logger.debug('exportUserDataToFile failed: truncated body');
      return null;
    }
    if (received < _exportCompletionSuffix.length || !_listEquals(tail, _exportCompletionSuffix)) {
      Logger.debug('exportUserDataToFile failed: missing export completion marker');
      return null;
    }

    await output.close();
    output = null;
    if (abort.isCompleted) {
      Logger.debug('exportUserDataToFile aborted');
      return null;
    }
    if (snapshot != null && !service.isSessionSnapshotCurrent(snapshot)) {
      Logger.debug('exportUserDataToFile aborted: session changed before promotion');
      return null;
    }
    await tempFile.rename(filePath);
    finished = true;
    return filePath;
  } catch (e) {
    Logger.debug('exportUserDataToFile error: ${e.runtimeType}');
    return null;
  } finally {
    await generationWatch?.cancel();
    if (!abort.isCompleted) abort.complete();
    final openOutput = output;
    if (openOutput != null) {
      try {
        await openOutput.close();
      } catch (_) {}
    }
    if (!finished) {
      try {
        if (await tempFile.exists()) await tempFile.delete();
      } catch (_) {}
    }
  }
}

bool _listEquals(List<int> a, List<int> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}
