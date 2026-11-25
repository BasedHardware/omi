// Owns strict installed-loader wire decoding and fresh session evidence.
// Missing or stale evidence is unknown; app versions never identify the loader.
import 'dart:typed_data';

/// Measured installed loader bytes, not an app version or a qualification verdict.
class BootloaderFingerprint {
  const BootloaderFingerprint._(this.status, this.sha256);
  final int status;
  final String? sha256;

  static BootloaderFingerprint? parse(List<int> bytes) {
    if (bytes.length != 44 || bytes.any((byte) => byte < 0 || byte > 255)) return null;
    final data = ByteData.sublistView(Uint8List.fromList(bytes));
    if (bytes[0] != 1 ||
        bytes[1] > 4 ||
        bytes[2] != 1 ||
        bytes[3] != 0 ||
        data.getUint32(4, Endian.little) != 0 ||
        data.getUint32(8, Endian.little) != 65536) {
      return null;
    }
    final digest = bytes.sublist(12);
    if (bytes[1] != 1) {
      if (digest.any((byte) => byte != 0)) return null;
      return BootloaderFingerprint._(bytes[1], null);
    }
    return BootloaderFingerprint._(1, digest.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join());
  }
}

bool isBootloaderSha256(String? value) => value != null && RegExp(r'^[0-9a-f]{64}$').hasMatch(value);

/// Each caller captures a live connection and validates it across every await.
/// There is deliberately no persistent or firmware-version-derived fingerprint.
class FirmwareDeviceSession {
  FirmwareDeviceSession(
      {required this.deviceId,
      required bool Function() isCurrent,
      required Future<List<int>?> Function() readFingerprint})
      : _isCurrent = isCurrent,
        _readFingerprint = readFingerprint;
  final String deviceId;
  final bool Function() _isCurrent;
  final Future<List<int>?> Function() _readFingerprint;
  bool get isCurrent => _isCurrent();

  Future<String?> readBootloaderSha256() async {
    if (!isCurrent) return null;
    try {
      final bytes = await _readFingerprint().timeout(const Duration(seconds: 3));
      if (!isCurrent || bytes == null) return null;
      return BootloaderFingerprint.parse(bytes)?.sha256;
    } catch (_) {
      // Old firmware/missing characteristic/failed read is unknown, never qualified.
      return null;
    }
  }
}
