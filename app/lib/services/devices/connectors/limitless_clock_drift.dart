/// Type-8 pendant clock parse + flash-page timestamp correction for #5734.
///
/// Pure helpers so the wire parser and correction math can be unit-tested
/// without a BLE stack. The Limitless RTC can diverge from phone wall clock
/// while offline; flash pages keep the RTC they were written under. Measuring
/// pendant−phone *before* SetCurrentTime lets batch WAL filenames overlap
/// real-time conversations so backend merge (`get_closest_conversation_to_timestamps`)
/// dedupes instead of creating a second conversation.
class LimitlessClockDrift {
  LimitlessClockDrift._();

  /// 2020-01-01 UTC — same sanity floor used by flash-page parsers.
  static const int minValidEpochMs = 1577836800000;

  /// Reject Type-8 readings that are not a plausible RTC offset.
  static const int maxAbsDriftMs = 7 * 24 * 60 * 60 * 1000;

  static bool isUsableDeviceTimestamp(int? timestampMs) {
    return timestampMs != null && timestampMs > minValidEpochMs;
  }

  /// Pendant RTC minus phone wall clock. Null when the reading is unusable.
  static int? measureClockDriftOffsetMs({required int pendantEpochMs, required int phoneEpochMs}) {
    if (!isUsableDeviceTimestamp(pendantEpochMs) || !isUsableDeviceTimestamp(phoneEpochMs)) {
      return null;
    }
    final drift = pendantEpochMs - phoneEpochMs;
    if (drift.abs() > maxAbsDriftMs) return null;
    return drift;
  }

  /// Subtract connect-time drift from a pendant flash-page RTC.
  ///
  /// When [pageTimestampMs] is missing or not a real pendant epoch, returns
  /// [phoneNowMs] unchanged — the `DateTime.now()` fallback is already phone
  /// time and must not be double-corrected.
  static int correctedFlashPageTimestampMs({
    required int? pageTimestampMs,
    required int? clockDriftOffsetMs,
    required int phoneNowMs,
  }) {
    if (!isUsableDeviceTimestamp(pageTimestampMs)) return phoneNowMs;
    return pageTimestampMs! - (clockDriftOffsetMs ?? 0);
  }

  /// Parses Type-8 pendant clock (epoch ms) from a BLE notification or payload.
  ///
  /// Accepted shapes (#5734 / observed firmware):
  /// - BLE wrapper f4 payload → f8 inner → f6 EPOCH_MS (varint)
  /// - f8 → f6 length-delimited → f1 EPOCH_MS (SetCurrentTime mirror)
  /// - f1=8 (message type) with sibling f6 EPOCH_MS
  ///
  /// Returns null for mode-only Type-8 (f8 with f1/f2 flags, no clock),
  /// unterminated varints, or epochs below [minValidEpochMs].
  static int? extractType8PendantEpochMs(List<int> data) {
    if (data.isEmpty) return null;
    try {
      return _findType8Epoch(data);
    } catch (_) {
      return null;
    }
  }

  static int? _findType8Epoch(List<int> data) {
    var pos = 0;
    int? typeField;
    int? siblingField6;

    while (pos < data.length) {
      final tag = data[pos];
      final fieldNum = tag >> 3;
      final wireType = tag & 0x07;
      pos++;
      if (fieldNum <= 0) break;

      if (wireType == 0) {
        final decoded = _decodeVarint(data, pos);
        final value = decoded.$1;
        if (value == null) return null;
        pos = decoded.$2;
        if (fieldNum == 1) typeField = value;
        if (fieldNum == 6) siblingField6 = value;
      } else if (wireType == 2) {
        final decoded = _decodeVarint(data, pos);
        final length = decoded.$1;
        if (length == null || length < 0 || decoded.$2 + length > data.length) {
          return null;
        }
        pos = decoded.$2;
        final inner = data.sublist(pos, pos + length);
        pos += length;
        if (fieldNum == 8) {
          final epoch = _extractEpochFromType8Inner(inner);
          if (epoch != null) return epoch;
        } else if (fieldNum == 4) {
          final epoch = _findType8Epoch(inner);
          if (epoch != null) return epoch;
        }
      } else if (wireType == 1) {
        pos += 8;
      } else if (wireType == 5) {
        pos += 4;
      } else {
        break;
      }
    }

    if (typeField == 8 && isUsableDeviceTimestamp(siblingField6)) {
      return siblingField6;
    }
    return null;
  }

  static int? _extractEpochFromType8Inner(List<int> inner) {
    var pos = 0;
    while (pos < inner.length) {
      final tag = inner[pos];
      final fieldNum = tag >> 3;
      final wireType = tag & 0x07;
      pos++;
      if (fieldNum <= 0) break;

      if (wireType == 0) {
        final decoded = _decodeVarint(inner, pos);
        final value = decoded.$1;
        if (value == null) return null;
        pos = decoded.$2;
        if (fieldNum == 6 && isUsableDeviceTimestamp(value)) return value;
      } else if (wireType == 2) {
        final decoded = _decodeVarint(inner, pos);
        final length = decoded.$1;
        if (length == null || length < 0 || decoded.$2 + length > inner.length) {
          return null;
        }
        pos = decoded.$2;
        final nested = inner.sublist(pos, pos + length);
        pos += length;
        if (fieldNum == 6) {
          final epoch = _extractField1Varint(nested);
          if (epoch != null) return epoch;
        }
      } else if (wireType == 1) {
        pos += 8;
      } else if (wireType == 5) {
        pos += 4;
      } else {
        break;
      }
    }
    return null;
  }

  static int? _extractField1Varint(List<int> data) {
    var pos = 0;
    while (pos < data.length) {
      final tag = data[pos];
      final fieldNum = tag >> 3;
      final wireType = tag & 0x07;
      pos++;
      if (fieldNum <= 0) break;

      if (wireType == 0) {
        final decoded = _decodeVarint(data, pos);
        final value = decoded.$1;
        if (value == null) return null;
        pos = decoded.$2;
        if (fieldNum == 1 && isUsableDeviceTimestamp(value)) return value;
      } else if (wireType == 2) {
        final decoded = _decodeVarint(data, pos);
        final length = decoded.$1;
        if (length == null || length < 0 || decoded.$2 + length > data.length) {
          return null;
        }
        pos = decoded.$2 + length;
      } else if (wireType == 1) {
        pos += 8;
      } else if (wireType == 5) {
        pos += 4;
      } else {
        break;
      }
    }
    return null;
  }

  /// Returns `(value, nextPos)` or `(null, startPos)` for unterminated/overlong.
  static (int?, int) _decodeVarint(List<int> data, int startPos) {
    var result = 0;
    var shift = 0;
    var pos = startPos;
    while (pos < data.length) {
      final byte = data[pos];
      pos++;
      result |= (byte & 0x7f) << shift;
      if ((byte & 0x80) == 0) return (result, pos);
      shift += 7;
      // protobuf int64 varints are at most 10 bytes.
      if (shift > 63) return (null, startPos);
    }
    return (null, startPos);
  }
}
