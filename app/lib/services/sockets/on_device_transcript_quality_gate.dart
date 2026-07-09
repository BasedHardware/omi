import 'dart:typed_data';

class OnDeviceTranscriptQualityGate {
  static const Set<String> _fillerOnlyTokens = {
    'no',
    'nope',
    'nah',
    'uh',
    'um',
    'hmm',
  };
  static const int _lowEnergyAverageAbsThreshold = 180;

  String? _lastAcceptedFiller;

  String? filter(String text, {required Uint8List audioData, required Duration duration}) {
    final cleaned = _clean(text);
    if (cleaned.isEmpty) return null;

    final normalized = _normalize(cleaned);
    if (_isFillerOnly(normalized)) {
      if (_isLowEnergyPcm(audioData)) return null;
      if (_lastAcceptedFiller == normalized) return null;
      _lastAcceptedFiller = normalized;
      return cleaned;
    }

    _lastAcceptedFiller = null;
    return cleaned;
  }

  static String _clean(String text) {
    return text
        .replaceAll(RegExp(r'\[.*?\]'), '')
        .replaceAll(RegExp(r'\(.*?\)'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  static String _normalize(String text) {
    return text
        .toLowerCase()
        .replaceAll(RegExp(r"[^\p{L}\p{N}\s']+", unicode: true), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  static bool _isFillerOnly(String normalized) => _fillerOnlyTokens.contains(normalized);

  static bool _isLowEnergyPcm(Uint8List bytes) {
    if (bytes.lengthInBytes < 2) return true;
    final dataOffset = _wavDataOffset(bytes) ?? 0;
    if (bytes.lengthInBytes - dataOffset < 2) return true;

    final data = ByteData.sublistView(bytes);
    var totalAbs = 0;
    var samples = 0;
    for (var i = dataOffset; i + 1 < bytes.lengthInBytes; i += 2) {
      totalAbs += data.getInt16(i, Endian.little).abs();
      samples += 1;
    }
    if (samples == 0) return true;
    return (totalAbs / samples) < _lowEnergyAverageAbsThreshold;
  }

  static int? _wavDataOffset(Uint8List bytes) {
    for (var i = 12; i + 8 <= bytes.lengthInBytes; i += 1) {
      if (bytes[i] == 0x64 && bytes[i + 1] == 0x61 && bytes[i + 2] == 0x74 && bytes[i + 3] == 0x61) {
        return i + 8;
      }
    }
    return null;
  }
}
