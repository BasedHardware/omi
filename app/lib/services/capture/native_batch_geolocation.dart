import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/schema/geolocation.dart';

const String nativeBatchGeolocationSidecarSuffix = '.geolocation.json';
const int nativeBatchGeolocationMaxBytes = 4096;

String nativeBatchGeolocationSidecarPath(String audioPath) => '$audioPath$nativeBatchGeolocationSidecarSuffix';

typedef NativeBatchGeolocationPreferenceWriter = Future<void> Function(Geolocation? geolocation);

/// Serializes the shared native phone-batch location preference and fences
/// writes by session. A delayed location result from session A can therefore
/// never repopulate the preference after session B has cleared it.
class NativeBatchGeolocationPreferenceFence {
  NativeBatchGeolocationPreferenceFence({required NativeBatchGeolocationPreferenceWriter writer}) : _writer = writer;

  final NativeBatchGeolocationPreferenceWriter _writer;
  Future<void> _writeTail = Future<void>.value();
  int _generation = 0;

  int beginSession() => ++_generation;

  void invalidateSession() {
    _generation++;
  }

  bool isCurrent(int generation) => generation == _generation;

  Future<void> writeIfCurrent(int generation, Geolocation? geolocation) {
    final write = _writeTail.then<void>((_) async {
      if (!isCurrent(generation)) return;
      await _writer(geolocation);
    });
    _writeTail = write.catchError((_) {});
    return write;
  }
}

/// Reads the private start-location snapshot copied by the native phone-batch
/// writer when it opens the corresponding audio file. Missing, oversized, or
/// malformed sidecars fail soft so recording discovery and upload still work.
Future<Geolocation?> readNativeBatchGeolocation(String audioPath) async {
  try {
    final sidecar = File(nativeBatchGeolocationSidecarPath(audioPath));
    if (!await sidecar.exists()) return null;
    final bytes = <int>[];
    await for (final chunk in sidecar.openRead(0, nativeBatchGeolocationMaxBytes + 1)) {
      bytes.addAll(chunk);
      if (bytes.length > nativeBatchGeolocationMaxBytes) return null;
    }
    if (bytes.isEmpty) return null;
    final decoded = jsonDecode(utf8.decode(bytes));
    if (decoded is! Map<String, dynamic>) return null;
    return Geolocation.fromJson(decoded);
  } catch (_) {
    return null;
  }
}
