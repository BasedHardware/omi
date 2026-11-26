import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/vendor_live_words.dart';
import 'package:omi/services/sockets/pure_socket.dart';

// Reliability experiment vendor_recognizer_on_opened_app: the phone's end of the display-only
// live-words connection. Audio comes from the capture taps; a connection exists only while capture is
// active and the app is in front; the last 3 s go first; lines come back on the phone's capture clock.

class FakeSocket implements IPureSocket {
  FakeSocket(this.url);

  final String url;
  final List<Object?> sent = [];
  IPureSocketListener? listener;
  bool connectResult = true;
  bool autoConnect = true;
  int stops = 0;

  @override
  PureSocketStatus status = PureSocketStatus.notConnected;

  @override
  void setListener(IPureSocketListener listener) => this.listener = listener;

  @override
  Future<bool> connect() async {
    if (!connectResult) return false;
    if (autoConnect) open();
    return true;
  }

  void open() {
    status = PureSocketStatus.connected;
    listener?.onConnected();
  }

  void serverSays(Map<String, Object?> message) => listener?.onMessage(jsonEncode(message));
  void serverCloses(int code) {
    status = PureSocketStatus.disconnected;
    listener?.onClosed(code);
  }

  @override
  Future disconnect() async => stops++;
  @override
  Future stop() async {
    stops++;
    status = PureSocketStatus.disconnected;
    listener?.onClosed(1000); // PureSocket reports its own close to the listener too.
  }

  @override
  void send(dynamic message) => sent.add(message);
  @override
  void onClosed() {}
  @override
  void onConnected() {}
  @override
  void onError(Object err, StackTrace trace) {}
  @override
  void onMessage(dynamic message) {}
}

/// A 20 ms SILK wideband Opus packet (config 9, one frame) behind the pendant's 3-byte header.
List<int> pendantPacket(int marker) => [0, 0, 0, 9 << 3, marker];

void main() {
  late List<FakeSocket> sockets;
  late List<List<LivePreviewLine>> received;
  late List<String> logged;
  late VendorLiveWords vendor;
  var clock = DateTime.utc(2026, 11, 25, 12);
  var connectResult = true;
  var autoConnect = true;

  void tick([int ms = 20]) => clock = clock.add(Duration(milliseconds: ms));

  /// [count] pendant packets, 20 ms apart, the clock moving with them.
  void speak(int count, {int from = 0}) {
    for (var i = 0; i < count; i++) {
      tick();
      vendor.onPendantPacket(pendantPacket((from + i) % 256), BleAudioCodec.opusFS320);
    }
  }

  setUp(() {
    sockets = [];
    received = [];
    logged = [];
    clock = DateTime.utc(2026, 11, 25, 12);
    connectResult = true;
    autoConnect = true;
    vendor = VendorLiveWords(
      onLines: received.add,
      connect: (url) {
        final socket = FakeSocket(url)
          ..connectResult = connectResult
          ..autoConnect = autoConnect;
        sockets.add(socket);
        return socket;
      },
      now: () => clock,
      baseUrl: () => 'ws://server/',
      uid: () => 'owner',
      log: (event, fields) => logged.add(event),
    );
  });

  test('an Opus packet says how long it is', () {
    expect(VendorLiveWords.opusPacketMs([9 << 3]), 20);
    expect(VendorLiveWords.opusPacketMs([8 << 3]), 10);
    expect(VendorLiveWords.opusPacketMs([(9 << 3) | 1]), 40);
    expect(VendorLiveWords.opusPacketMs([(9 << 3) | 3, 3]), 60);
    expect(VendorLiveWords.opusPacketMs([31 << 3]), 20);
    expect(VendorLiveWords.opusPacketMs([16 << 3]), 2.5);
    expect(VendorLiveWords.opusPacketMs([]), isNull);
  });

  test('nothing is kept or sent while capture is not active', () async {
    speak(50);
    expect(vendor.ringFramesForTesting, 0);
    expect(sockets, isEmpty);
  });

  test('capturing in the background fills the lead-in and opens no connection', () async {
    vendor.setState(capturing: true, inFront: false, language: 'en');
    speak(400); // 8 s
    expect(sockets, isEmpty);
    expect(vendor.ringFramesForTesting, 150); // the last 3 s
  });

  test('coming to the front dials on the next frame and sends the last 3 s first', () async {
    vendor.setState(capturing: true, inFront: false, language: 'en');
    speak(400);
    vendor.setState(capturing: true, inFront: true, language: 'en');
    expect(sockets, isEmpty); // No audio, no dial.
    speak(1, from: 144);
    await pumpEventQueue();
    final socket = sockets.single;
    expect(socket.url, 'ws://server/v4/live-words?language=en&sample_rate=16000&codec=opus&uid=owner');
    // 150 frames of lead-in (the newest of them is the frame that dialled), without the pendant's header.
    expect(socket.sent, hasLength(150));
    expect(socket.sent.first, isA<Uint8List>().having((bytes) => bytes.length, 'payload length', 2));
    speak(5);
    expect(socket.sent, hasLength(155));
    expect(vendor.sentMs, 155 * 20);
  });

  test('lines come back on the capture clock of the frame that carried them', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    final start = clock; // The first frame's first sample is captured now.
    speak(250); // 5 s
    await pumpEventQueue();
    sockets.single.serverSays({
      'type': 'lines',
      'lines': [
        {
          'id': 'abc',
          'speaker': 'SPEAKER_00',
          'start': 1.0,
          'end': 2.5,
          'text': ' hello there ',
          'words': [
            ['hello', 1.0, 1.4],
            ['there', 2.0, 2.5],
          ],
        }
      ],
    });
    final line = received.single.single;
    expect(line.id, 'vendor:1:abc');
    expect(line.text, 'hello there');
    expect(line.isFinal, isTrue);
    expect(line.startedAt, start.add(const Duration(milliseconds: 1000)));
    expect(line.endedAt, start.add(const Duration(milliseconds: 2500)));
    expect(line.spans.map((span) => span.text), ['hello', 'there']);
    expect(line.spans.last.startedAt, start.add(const Duration(seconds: 2)));
    expect(vendor.linesReceived, 1);
  });

  test('a lead-in sent at once is still timed where it was captured', () async {
    vendor.setState(capturing: true, inFront: false, language: 'en');
    speak(400); // 8 s in the background
    final leadInStart = clock.subtract(const Duration(milliseconds: 3000));
    vendor.setState(capturing: true, inFront: true, language: 'en');
    tick(60000 - 20); // The pendant was silent on the air for a minute (no frames).
    speak(1);
    await pumpEventQueue();
    sockets.single.serverSays({
      'type': 'lines',
      'lines': [
        {'id': 'a', 'start': 0.5, 'end': 1.0, 'text': 'before', 'words': []},
        {'id': 'b', 'start': 2.98, 'end': 3.0, 'text': 'after', 'words': []},
      ],
    });
    final lines = received.single;
    // 0.5 s into the connection is 0.5 s into the lead-in, not 0.5 s after the connection opened.
    expect(lines[0].startedAt, leadInStart.add(const Duration(milliseconds: 520)));
    // The frame that dialled was captured a minute later; its audio sits there, not right after the lead-in.
    expect(lines[1].startedAt!.difference(leadInStart).inSeconds, 62);
  });

  test('leaving the front closes the connection; pausing or stopping also drops the lead-in', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(10);
    await pumpEventQueue();
    final first = sockets.single;
    vendor.setState(capturing: true, inFront: false, language: 'en');
    expect(first.stops, 1);
    expect(vendor.connected, isFalse);
    speak(10);
    expect(sockets, hasLength(1));
    expect(vendor.ringFramesForTesting, 20);

    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(1);
    await pumpEventQueue();
    expect(sockets, hasLength(2));
    // Audio the first connection carried is not sent again: only what came after it.
    expect(sockets[1].sent, hasLength(11));
    vendor.setState(capturing: false, inFront: false, language: 'en');
    expect(sockets[1].stops, 1);
    expect(vendor.ringFramesForTesting, 0);
    expect(logged.where((event) => event == 'close'), hasLength(2));
  });

  test('a lost connection is redialled by later audio, after a wait that grows', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(5);
    await pumpEventQueue();
    sockets[0].serverCloses(1011);
    speak(40); // 0.8 s: inside the 1 s wait
    expect(sockets, hasLength(1));
    speak(15);
    await pumpEventQueue();
    expect(sockets, hasLength(2));
    sockets[1].serverCloses(1011);
    speak(75); // 1.5 s: inside the 2 s wait
    expect(sockets, hasLength(2));
    speak(30);
    await pumpEventQueue();
    expect(sockets, hasLength(3));
    // An acknowledged connection earns a quick retry again.
    sockets[2].serverSays({'type': 'ack', 'frames': 10, 'audio_ms': 200});
    sockets[2].serverCloses(1011);
    speak(55);
    await pumpEventQueue();
    expect(sockets, hasLength(4));
  });

  test('a refused dial backs off and never loops', () async {
    connectResult = false;
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(50 * 20); // 20 s of audio
    await pumpEventQueue();
    // Waits of 1, 2, 4, 8 s: five dials fit in 20 s, not one per frame.
    expect(sockets.length, lessThanOrEqualTo(5));
    expect(sockets.every((socket) => socket.sent.isEmpty), isTrue);
  });

  test('the server refusing the stream, or replacing it, is not fought', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(5);
    await pumpEventQueue();
    sockets[0].serverCloses(VendorLiveWords.closeReplaced);
    speak(50 * 20); // 20 s
    await pumpEventQueue();
    expect(sockets, hasLength(1));
    speak(50 * 15); // past 30 s
    await pumpEventQueue();
    expect(sockets, hasLength(2));
    sockets[1].serverCloses(VendorLiveWords.closeRefused);
    speak(50 * 120); // 2 minutes
    await pumpEventQueue();
    expect(sockets, hasLength(2));
  });

  test('an idle close is followed by a dial on the next audio', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(5);
    await pumpEventQueue();
    sockets[0].serverCloses(VendorLiveWords.closeIdle);
    tick(60000);
    speak(1);
    await pumpEventQueue();
    expect(sockets, hasLength(2));
  });

  test('audio the server stops confirming is dropped with its connection, never queued without bound', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(100);
    await pumpEventQueue();
    sockets[0].serverSays({'type': 'ack', 'frames': 100, 'audio_ms': 2000});
    speak(50 * 11); // 11 s with no further ack: more than the 10 s allowed
    expect(sockets[0].stops, greaterThanOrEqualTo(1));
    expect(vendor.droppedConnections, 1);
    expect(vendor.connected, isFalse);
    speak(60); // past the 1 s wait
    await pumpEventQueue();
    expect(sockets, hasLength(2));
  });

  test('the phone microphone is another stream: PCM gets its own connection', () async {
    vendor.setState(capturing: true, inFront: true, language: 'multi');
    speak(5);
    await pumpEventQueue();
    tick();
    vendor.onPhonePcm(List.filled(640, 1));
    await pumpEventQueue();
    expect(sockets[0].stops, 1);
    expect(sockets[1].url, contains('codec=pcm16'));
    expect(sockets[1].url, contains('language=multi'));
    expect(sockets[1].sent.single, hasLength(640));
  });

  test('a message that is not what the server sends is ignored', () async {
    vendor.setState(capturing: true, inFront: true, language: 'en');
    speak(5);
    await pumpEventQueue();
    sockets[0].listener!.onMessage('not json');
    sockets[0].serverSays({'type': 'lines', 'lines': 'nope'});
    sockets[0].serverSays({
      'type': 'lines',
      'lines': [
        {'id': 1, 'text': 'x', 'start': 0, 'end': 1},
        {'id': 'a', 'text': '   ', 'start': 0, 'end': 1},
      ],
    });
    expect(received, isEmpty);
  });
}
