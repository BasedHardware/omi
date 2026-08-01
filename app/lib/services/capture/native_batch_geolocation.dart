import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/schema/geolocation.dart';

const String nativeBatchGeolocationSidecarSuffix = '.geolocation.json';
const int nativeBatchGeolocationMaxBytes = 4096;

String nativeBatchGeolocationSidecarPath(String audioPath) => '$audioPath$nativeBatchGeolocationSidecarSuffix';

/// Reads the private start-location snapshot copied by the native phone-batch
/// writer when it opens the corresponding audio file. Missing, oversized, or
/// malformed sidecars fail soft so recording discovery and upload still work.
Future<Geolocation?> readNativeBatchGeolocation(String audioPath) async {
  try {
    final sidecar = File(nativeBatchGeolocationSidecarPath(audioPath));
    if (!await sidecar.exists()) return null;
    final bytes = await sidecar.readAsBytes();
    if (bytes.isEmpty || bytes.length > nativeBatchGeolocationMaxBytes) return null;
    final decoded = jsonDecode(utf8.decode(bytes));
    if (decoded is! Map<String, dynamic>) return null;
    return Geolocation.fromJson(decoded);
  } catch (_) {
    return null;
  }
}
