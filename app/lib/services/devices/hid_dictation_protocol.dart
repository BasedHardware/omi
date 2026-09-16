import 'dart:typed_data';

/// Wire mirror of the pendant firmware's HID dictation protocol
/// (omi/firmware/omi/src/lib/core/hid_dictation.h). Keep both sides in sync.
///
/// Service 19b10040-e8f2-537e-4f6c-d104768a1214
///   - Control 19b10041: read/notify status struct, write 1-byte command.
///   - Text     19b10042: write-with-response frames
///     [session:1][flags:1][len:1][payload:len].
class HidDictationProtocol {
  static const int protocolVersion = 1;

  // Frame flags.
  static const int flagFinal = 0x01;
  static const int flagCancel = 0x02;

  // Control commands.
  static const int cmdEnable = 0x01;
  static const int cmdDisable = 0x02;

  // States (enum hid_dictation_state).
  static const int stateDisabled = 0;
  static const int stateIdle = 1;
  static const int stateReceiving = 2;
  static const int stateTyping = 3;
  static const int stateDone = 4;
  static const int stateError = 5;

  // Errors (enum hid_dictation_error).
  static const int errNone = 0;
  static const int errUnsupportedChar = 1;
  static const int errBusy = 2;
  static const int errBadFrame = 3;
  static const int errTooLong = 4;
  static const int errTimeout = 5;
  static const int errNotEnabled = 6;
  static const int errDuplicateSession = 7;
  static const int errNotSubscribed = 8;
  static const int errCancelled = 9;
  static const int errInternal = 10;

  /// Session id 0 is never a valid data session.
  static const int sessionNone = 0;

  /// Conservative per-frame payload: 17 bytes fit a 23-byte ATT MTU (the
  /// pre-exchange default) with the 3-byte header and 3-byte ATT opcode left.
  /// iOS frequently negotiates only 185 (182 usable), and the transport does
  /// NOT split application-level writes — frames must fit the *worst* link.
  static const int maxFramePayload = 17;

  /// Maximum committed text the firmware will type (mirror of
  /// CONFIG_OMI_HID_DICTATION_MAX_TEXT_LEN default).
  static const int maxTextLength = 256;

  HidDictationProtocol._();

  /// Printable US ASCII plus space is the entire supported alphabet.
  /// Controls, DEL, and anything non-ASCII are rejected explicitly — the
  /// prototype never transliterates or silently truncates.
  static bool isCharSupported(int codeUnit) => codeUnit >= 0x20 && codeUnit <= 0x7E;

  /// Returns the first unsupported index, or null when the whole text is good.
  static int? firstUnsupportedIndex(String text) {
    for (int i = 0; i < text.length; i++) {
      if (!isCharSupported(text.codeUnitAt(i))) return i;
    }
    return null;
  }

  /// Splits [text] into ordered frames for [session].
  ///
  /// Fails closed: throws [ArgumentError] instead of silently filtering —
  /// a caller that has not validated the text must not get mangled frames
  /// (asserts are stripped in release mode, so filtering would ship).
  static List<Uint8List> buildFrames(int session, String text, {int maxPayload = maxFramePayload}) {
    if (session == sessionNone || session < 1 || session > 255) {
      throw ArgumentError.value(session, 'session', 'must be 1..255 (0 is reserved)');
    }
    if (maxPayload < 1 || maxPayload > 244) {
      throw ArgumentError.value(maxPayload, 'maxPayload', 'must be 1..244 (firmware frame bound)');
    }
    if (text.length > maxTextLength) {
      throw ArgumentError.value(text.length, 'text.length', 'exceeds firmware max $maxTextLength');
    }
    final bad = firstUnsupportedIndex(text);
    if (bad != null) {
      throw ArgumentError.value(text.codeUnitAt(bad), 'text[$bad]', 'unsupported character (reject whole text first)');
    }

    final bytes = text.codeUnits;
    if (bytes.isEmpty) return const [];

    final frames = <Uint8List>[];
    for (int offset = 0; offset < bytes.length; offset += maxPayload) {
      final end = (offset + maxPayload) < bytes.length ? offset + maxPayload : bytes.length;
      final payload = bytes.sublist(offset, end);
      final isLast = end == bytes.length;
      final frame = Uint8List(3 + payload.length);
      frame[0] = session & 0xFF;
      frame[1] = isLast ? flagFinal : 0x00;
      frame[2] = payload.length;
      frame.setAll(3, payload);
      frames.add(frame);
    }
    return frames;
  }

  /// A one-byte cancel frame. [session] 0 cancels whatever the firmware is
  /// running; otherwise it must match the active session.
  static Uint8List buildCancelFrame([int session = sessionNone]) {
    return Uint8List.fromList([session & 0xFF, flagCancel, 0]);
  }

  /// Parses the 10-byte status payload. Fails closed: null on truncated
  /// payloads or an unknown protocol version (the peer speaks a wire format
  /// this build cannot interpret).
  static HidDictationStatus? parseStatus(Uint8List data) {
    if (data.length < 10) return null;
    if (data[0] != protocolVersion) return null;
    final view = ByteData.view(data.buffer, data.offsetInBytes, data.length);
    return HidDictationStatus(
      version: data[0],
      state: data[1],
      hidActive: data[2] != 0,
      hidPending: data[3] != 0,
      lastError: data[4],
      errorDetail: data[5],
      activeSession: data[6],
      lastFinishedSession: data[7],
      charsTyped: view.getUint16(8, Endian.little),
    );
  }
}

/// Mirror of struct hid_dictation_status.
class HidDictationStatus {
  final int version;
  final int state;
  final bool hidActive;
  final bool hidPending;
  final int lastError;
  final int errorDetail;
  final int activeSession;
  final int lastFinishedSession;
  final int charsTyped;

  const HidDictationStatus({
    required this.version,
    required this.state,
    required this.hidActive,
    required this.hidPending,
    required this.lastError,
    required this.errorDetail,
    required this.activeSession,
    required this.lastFinishedSession,
    required this.charsTyped,
  });

  bool get isTyping => state == HidDictationProtocol.stateTyping;
  bool get isError => state == HidDictationProtocol.stateError;
  bool get wasCancelled => lastError == HidDictationProtocol.errCancelled;

  String describe() {
    switch (lastError) {
      case HidDictationProtocol.errUnsupportedChar:
        return 'unsupported character at $errorDetail';
      case HidDictationProtocol.errBusy:
        return 'busy (session $errorDetail active)';
      case HidDictationProtocol.errBadFrame:
        return 'bad frame';
      case HidDictationProtocol.errTooLong:
        return 'text too long';
      case HidDictationProtocol.errTimeout:
        return 'timeout';
      case HidDictationProtocol.errNotEnabled:
        return 'HID prototype not active';
      case HidDictationProtocol.errDuplicateSession:
        return 'duplicate session $errorDetail';
      case HidDictationProtocol.errNotSubscribed:
        return 'no HID host subscribed';
      case HidDictationProtocol.errCancelled:
        return 'cancelled';
      case HidDictationProtocol.errInternal:
        return 'internal error';
      case HidDictationProtocol.errNone:
      default:
        return 'ok';
    }
  }
}
