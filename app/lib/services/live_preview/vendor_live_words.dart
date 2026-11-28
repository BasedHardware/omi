import 'dart:collection';
import 'dart:convert';
import 'dart:typed_data';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/sockets/pure_socket.dart';

/// Reliability experiment `vendor_recognizer_on_opened_app`: the phone's end of the display-only
/// live-words connection (backend/routers/listen/live_words.py).
///
/// It listens on the same capture audio taps as the phone's own recogniser and sends a COPY of the
/// audio on its own WebSocket, apart from the listening connection and from the phone files that
/// carry the record. Capture never waits on it: a tap callback only appends to a small ring, and
/// when the connection falls behind, display audio is dropped, never capture audio.
///
/// The connection is open only while capture is active and the app is in front ([setState]). It
/// keeps the last [leadIn] of audio and sends that first when it opens, so the sentence in progress
/// is not cut. It reconnects with a growing wait, started by the next audio frame, so a stream with
/// no audio never dials.
///
/// The phone owns the clock: the server times a line in seconds of audio from the first frame of the
/// connection, and this class maps that to the capture time of the frame that carried it.
class VendorLiveWords implements IPureSocketListener {
  VendorLiveWords({
    required this.onLines,
    this.onAudioSent,
    IPureSocket Function(String url)? connect,
    DateTime Function()? now,
    String Function()? baseUrl,
    String Function()? uid,
    this.log,
    this.leadIn = const Duration(seconds: 3),
    this.maxBacklog = const Duration(seconds: 10),
    this.maxRetryWait = const Duration(minutes: 2),
  })  : _connect = connect ?? PureSocket.new,
        _now = now ?? DateTime.now,
        _baseUrl = baseUrl ?? _envBaseUrl,
        _uid = uid ?? (() => SharedPreferencesUtil().uid);

  /// New or longer lines, timed on the phone's capture clock.
  final void Function(List<LivePreviewLine> lines) onLines;

  /// Each frame the connection carried: when capture saw its first sample, and its length in
  /// milliseconds. Reliability experiment `live_words_cascade` counts from it; nobody else listens.
  final void Function(DateTime capturedAt, double ms)? onAudioSent;
  final void Function(String event, Map<String, Object?> fields)? log;
  final Duration leadIn;

  /// Audio sent that the server has not confirmed. Past this the connection is dropped and reopened.
  final Duration maxBacklog;

  /// The wait before another dial doubles from one second up to this.
  final Duration maxRetryWait;

  final IPureSocket Function(String url) _connect;
  final DateTime Function() _now;
  final String Function() _baseUrl;
  final String Function() _uid;

  static const closeReplaced = 4009;
  static const closeIdle = 4008;
  static const closeRefused = 1008;

  static String _envBaseUrl() =>
      (Env.apiBaseUrl ?? '').replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');

  bool _capturing = false;
  bool _inFront = false;
  String _language = 'multi';
  bool _disposed = false;

  bool get wanted => _capturing && _inFront && !_disposed;

  // The last [leadIn] of audio, whether or not a connection is open.
  final Queue<_Frame> _ring = Queue();
  double _ringMs = 0;
  String? _ringCodec;

  IPureSocket? _socket;
  bool _connected = false;
  String? _socketCodec;
  int _connections = 0;
  int _failures = 0;

  /// Capture time of the newest frame any connection has carried: a reconnect's lead-in starts after
  /// it, so the same audio is not recognised twice into two sets of lines.
  DateTime? _carriedUntil;
  DateTime? _nextConnectAt;
  DateTime? _connectedAt;

  // Audio sent on the open connection, and where each stretch of it sat on the capture clock.
  double _sentMs = 0;
  int _ackedMs = 0;
  double _lastAnchorMs = double.negativeInfinity;
  final List<(double, DateTime)> _anchors = [];
  static const _anchorEveryMs = 500.0;
  static const _anchorJumpMs = 100;
  static const _maxAnchors = 2400; // 20 minutes

  // Counters (local reliability measure; no text).
  int connectsForTesting = 0;
  int droppedConnections = 0;
  int linesReceived = 0;
  double totalSentMs = 0;

  bool get connected => _connected;
  double get sentMs => _sentMs;
  int get ackedMs => _ackedMs;
  int get ringFramesForTesting => _ring.length;

  /// Capture is active (not paused, not stopped) and whether the app is exactly in front.
  void setState({required bool capturing, required bool inFront, String? language}) {
    if (_disposed) return;
    if (language != null && language != _language) {
      _language = language;
      if (_socket != null) _close('language');
    }
    final was = wanted;
    _capturing = capturing;
    _inFront = inFront;
    if (!capturing) {
      _clearRing();
      _carriedUntil = null;
    }
    if (was && !wanted) {
      _close(capturing ? 'left_front' : 'capture_inactive');
      _failures = 0;
      _nextConnectAt = null;
    }
  }

  /// Pendant tap: a raw BLE packet including its three-byte transport header.
  void onPendantPacket(List<int> packet, BleAudioCodec codec) {
    if (!_capturing || packet.length <= 3) return;
    if (codec.isOpusSupported()) {
      final payload = Uint8List.fromList(packet.sublist(3));
      _frame(payload, 'opus', opusPacketMs(payload) ?? 1000 / codec.getFramesPerSecond());
    } else if (codec == BleAudioCodec.pcm16) {
      final payload = Uint8List.fromList(packet.sublist(3));
      _frame(payload, 'pcm16', payload.length / 32);
    }
  }

  /// Phone-mic tap: PCM16 16 kHz mono.
  void onPhonePcm(List<int> pcm) {
    if (!_capturing || pcm.isEmpty) return;
    _frame(Uint8List.fromList(pcm), 'pcm16', pcm.length / 32);
  }

  void dispose() {
    _disposed = true;
    _close('dispose');
    _clearRing();
  }

  // ------------------------------------------------------------------ audio --

  void _frame(Uint8List bytes, String codec, double ms) {
    final now = _now();
    if (_ringCodec != codec) {
      // Another source took over (pendant to phone microphone): its audio is another stream.
      _clearRing();
      _ringCodec = codec;
      if (_socket != null) _close('codec');
    }
    final frame = _Frame(bytes, now.subtract(Duration(microseconds: (ms * 1000).round())), ms);
    _ring.add(frame);
    _ringMs += ms;
    while (_ringMs - _ring.first.ms >= leadIn.inMilliseconds && _ring.length > 1) {
      _ringMs -= _ring.removeFirst().ms;
    }
    if (!wanted) return;
    if (_connected && _socketCodec == codec) {
      _send(frame);
      if (_sentMs - _ackedMs > maxBacklog.inMilliseconds && now.difference(_connectedAt ?? now) > maxBacklog) {
        // The server stopped confirming audio: drop the display audio and start again.
        droppedConnections++;
        _close('backlog');
        _retryAfterFailure(now);
      }
      return;
    }
    if (_socket == null && (_nextConnectAt == null || !now.isBefore(_nextConnectAt!))) _open(codec);
  }

  void _clearRing() {
    _ring.clear();
    _ringMs = 0;
    _ringCodec = null;
  }

  void _send(_Frame frame) {
    // An anchor every half second of audio, and at once where capture itself has a gap (packets lost
    // on the air, a lead-in followed by live audio): the audio after a gap sits where it was captured.
    final expected = _anchors.isEmpty
        ? null
        : _anchors.last.$2.add(Duration(microseconds: ((_sentMs - _anchors.last.$1) * 1000).round()));
    final off = expected == null ? 0 : frame.capturedAt.difference(expected).inMilliseconds.abs();
    // Packets that arrive in bursts wobble by a few tens of milliseconds; that is not a gap, and an
    // anchor per packet would push the older anchors out.
    final jumped = off > 1000 || (off > _anchorJumpMs && _sentMs - _lastAnchorMs >= 100);
    if (jumped || _sentMs - _lastAnchorMs >= _anchorEveryMs) {
      _anchors.add((_sentMs, frame.capturedAt));
      _lastAnchorMs = _sentMs;
      if (_anchors.length > _maxAnchors) _anchors.removeRange(0, _anchors.length - _maxAnchors);
    }
    _socket?.send(frame.bytes);
    _carriedUntil = frame.capturedAt;
    _sentMs += frame.ms;
    totalSentMs += frame.ms;
    onAudioSent?.call(frame.capturedAt, frame.ms);
  }

  // ---------------------------------------------------------------- the End --

  DateTime? _endPending;
  int endsSentForTesting = 0;

  /// Reliability experiment `live_words_cascade`: the person ended the conversation at [endedAt]. The
  /// server is told in the audio's own order (a text message between two frames), so it breaks the line
  /// in progress exactly there and no line spans two conversations. With no connection open the next
  /// one is told at the first frame captured after [endedAt]. A server without the experiment ignores
  /// the message.
  void markEnd(DateTime endedAt) {
    if (_disposed) return;
    if (_connected && _socket != null) {
      _sendEnd();
    } else {
      _endPending = endedAt;
    }
  }

  void _sendEnd() {
    _endPending = null;
    endsSentForTesting++;
    _socket?.send(jsonEncode(const {'type': 'end'}));
  }

  /// The capture time of the audio [seconds] into this connection.
  DateTime? _at(double seconds) {
    if (_anchors.isEmpty) return null;
    final ms = seconds * 1000;
    var low = 0, high = _anchors.length - 1;
    while (low < high) {
      final mid = (low + high + 1) >> 1;
      if (_anchors[mid].$1 <= ms) {
        low = mid;
      } else {
        high = mid - 1;
      }
    }
    final (anchorMs, anchorAt) = _anchors[low];
    return anchorAt.add(Duration(microseconds: ((ms - anchorMs) * 1000).round()));
  }

  // ------------------------------------------------------------- connection --

  void _open(String codec) {
    final uid = _uid();
    final url = '${_baseUrl()}v4/live-words?language=${Uri.encodeComponent(_language)}'
        '&sample_rate=16000&codec=$codec&uid=${Uri.encodeComponent(uid)}';
    final socket = _connect(url);
    _socket = socket;
    _socketCodec = codec;
    _connected = false;
    _connections++;
    connectsForTesting++;
    socket.setListener(this);
    final attempt = _connections;
    socket.connect().then((ok) {
      if (ok || attempt != _connections || !identical(_socket, socket)) return;
      // Refused before the handshake finished (server off, no network, no sign-in).
      _socket = null;
      _retryAfterFailure(_now());
      log?.call('connect_failed', {'failures': _failures});
    }).catchError((Object _) {
      if (attempt != _connections || !identical(_socket, socket)) return;
      _socket = null;
      _retryAfterFailure(_now());
    });
  }

  void _retryAfterFailure(DateTime now, {Duration? atLeast}) {
    _failures++;
    final seconds = 1 << (_failures - 1).clamp(0, 10);
    var wait = Duration(seconds: seconds);
    if (wait > maxRetryWait) wait = maxRetryWait;
    if (atLeast != null && wait < atLeast) wait = atLeast;
    _nextConnectAt = now.add(wait);
  }

  void _close(String reason) {
    final socket = _socket;
    if (socket == null) return;
    final seconds = _connectedAt == null ? 0.0 : _now().difference(_connectedAt!).inMilliseconds / 1000;
    log?.call('close', {
      'reason': reason,
      'connected_s': seconds,
      'sent_ms': _sentMs.round(),
      'acked_ms': _ackedMs,
    });
    _socket = null;
    _reset();
    // Never wait on the peer: the page the user is on must not depend on this stream.
    socket.stop();
  }

  void _reset() {
    _connected = false;
    _socketCodec = null;
    _connectedAt = null;
    _sentMs = 0;
    _ackedMs = 0;
    _lastAnchorMs = double.negativeInfinity;
    _anchors.clear();
  }

  @override
  void onConnected() {
    if (_socket == null) return;
    if (!wanted) return _close('not_wanted');
    _connected = true;
    _connectedAt = _now();
    log?.call('open', {'codec': _socketCodec, 'lead_in_ms': _ringMs.round(), 'connection': _connections});
    // The lead-in first: the sentence in progress, from its start.
    final carried = _carriedUntil;
    for (final frame in _ring) {
      if (carried != null && !frame.capturedAt.isAfter(carried)) continue;
      // An End pressed while no connection was open falls inside the lead-in: tell the server where.
      final end = _endPending;
      if (end != null && !frame.capturedAt.isBefore(end)) _sendEnd();
      _send(frame);
    }
    // Every frame sent was captured before the End: the line breaks before the next one.
    if (_endPending != null) _sendEnd();
  }

  @override
  void onMessage(dynamic message) {
    if (message is! String || !_connected) return;
    Object? payload;
    try {
      payload = jsonDecode(message);
    } catch (_) {
      return;
    }
    if (payload is! Map) return;
    switch (payload['type']) {
      case 'ack':
        final ms = payload['audio_ms'];
        if (ms is num) _ackedMs = ms.round();
        _failures = 0; // A connection that carries audio earns a quick retry next time.
      case 'lines':
        final lines = payload['lines'];
        if (lines is List) _lines(lines);
    }
  }

  void _lines(List<dynamic> wire) {
    final now = _now();
    final out = <LivePreviewLine>[];
    for (final item in wire) {
      if (item is! Map) continue;
      final id = item['id'], text = item['text'], start = item['start'], end = item['end'];
      if (id is! String || text is! String || start is! num || end is! num || text.trim().isEmpty) continue;
      final startedAt = _at(start.toDouble()), endedAt = _at(end.toDouble());
      if (startedAt == null || endedAt == null) continue;
      final spans = <LivePreviewSpan>[];
      final words = item['words'];
      if (words is List) {
        for (final word in words) {
          if (word is! List || word.length != 3) continue;
          final wordText = word[0], wordStart = word[1], wordEnd = word[2];
          if (wordText is! String || wordStart is! num || wordEnd is! num) continue;
          final from = _at(wordStart.toDouble()), to = _at(wordEnd.toDouble());
          if (from == null || to == null) continue;
          spans.add(LivePreviewSpan(text: wordText, startedAt: from, endedAt: to));
        }
      }
      out.add(LivePreviewLine(
        // Line ids are the server's per connection; keep them apart across reconnects.
        id: 'vendor:$_connections:$id',
        text: text.trim(),
        isFinal: true,
        startedAt: startedAt,
        endedAt: endedAt,
        firstSeenAt: now,
        spans: spans,
      ));
    }
    if (out.isEmpty) return;
    linesReceived += out.length;
    onLines(out);
  }

  @override
  void onClosed([int? closeCode]) {
    if (_socket == null) return; // Our own close.
    final seconds = _connectedAt == null ? 0.0 : _now().difference(_connectedAt!).inMilliseconds / 1000;
    log?.call('closed_by_server', {'code': closeCode, 'connected_s': seconds, 'sent_ms': _sentMs.round()});
    _socket = null;
    _reset();
    final now = _now();
    switch (closeCode) {
      case closeIdle:
        _nextConnectAt = null; // No audio was flowing; the next frame may dial at once.
      case closeRefused:
        // The server does not offer the stream (experiment off there): ask again rarely.
        _retryAfterFailure(now, atLeast: const Duration(minutes: 5));
      case closeReplaced:
        // Another connection from this install took over; do not fight it.
        _retryAfterFailure(now, atLeast: const Duration(seconds: 30));
      default:
        _retryAfterFailure(now);
    }
  }

  @override
  void onError(Object err, StackTrace trace) {
    if (_socket == null) return;
    log?.call('error', {'type': err.runtimeType.toString()});
    _socket = null;
    _reset();
    _retryAfterFailure(_now());
  }

  /// Duration of one Opus packet from its table-of-contents byte (RFC 6716, 3.1), or null when the
  /// packet cannot say.
  static double? opusPacketMs(List<int> packet) {
    if (packet.isEmpty) return null;
    final toc = packet[0];
    final config = toc >> 3;
    final double frameMs;
    if (config < 12) {
      frameMs = const [10.0, 20.0, 40.0, 60.0][config & 3];
    } else if (config < 16) {
      frameMs = const [10.0, 20.0][config & 1];
    } else {
      frameMs = const [2.5, 5.0, 10.0, 20.0][config & 3];
    }
    final int frames;
    switch (toc & 3) {
      case 0:
        frames = 1;
      case 1:
      case 2:
        frames = 2;
      default:
        if (packet.length < 2) return null;
        frames = packet[1] & 0x3f;
    }
    if (frames == 0) return null;
    return frameMs * frames;
  }
}

class _Frame {
  _Frame(this.bytes, this.capturedAt, this.ms);

  final Uint8List bytes;

  /// When capture saw the first sample of this frame.
  final DateTime capturedAt;
  final double ms;
}
