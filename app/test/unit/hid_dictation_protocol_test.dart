import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/hid_dictation_protocol.dart';

void main() {
  group('HidDictationProtocol text support', () {
    test('printable ASCII and space are supported', () {
      expect(HidDictationProtocol.firstUnsupportedIndex('Hello, world! 123'), isNull);
      final allPrintable = String.fromCharCodes(List<int>.generate(95, (i) => 0x20 + i));
      expect(HidDictationProtocol.firstUnsupportedIndex(allPrintable), isNull);
    });

    test('controls, DEL and non-ASCII are rejected with the first index', () {
      expect(HidDictationProtocol.firstUnsupportedIndex('hi\n'), 2);
      expect(HidDictationProtocol.firstUnsupportedIndex('ok\tdo'), 2);
      expect(HidDictationProtocol.firstUnsupportedIndex('é'), 0);
      expect(HidDictationProtocol.firstUnsupportedIndex('a\x7F'), 1);
      expect(HidDictationProtocol.firstUnsupportedIndex(''), isNull);
    });
  });

  group('HidDictationProtocol frames', () {
    test('single short text becomes one final frame', () {
      final frames = HidDictationProtocol.buildFrames(7, 'hi');
      expect(frames, hasLength(1));
      expect(frames.single[0], 7);
      expect(frames.single[1], HidDictationProtocol.flagFinal);
      expect(frames.single[2], 2);
      expect(frames.single.sublist(3), 'hi'.codeUnits);
    });

    test('long text chunks with final flag only on the last frame', () {
      final text = 'a' * 450; // 200 + 200 + 50
      final frames = HidDictationProtocol.buildFrames(9, text);
      expect(frames, hasLength(3));
      expect(frames[0][1], 0x00);
      expect(frames[0][2], 200);
      expect(frames[1][1], 0x00);
      expect(frames[1][2], 200);
      expect(frames[2][1], HidDictationProtocol.flagFinal);
      expect(frames[2][2], 50);
      final rebuilt = frames.map((f) => String.fromCharCodes(f.sublist(3))).join();
      expect(rebuilt, text);
    });

    test('empty text yields no frames and cancel frame is well-formed', () {
      expect(HidDictationProtocol.buildFrames(3, ''), isEmpty);
      final cancel = HidDictationProtocol.buildCancelFrame(3);
      expect(cancel, [3, HidDictationProtocol.flagCancel, 0]);
      expect(HidDictationProtocol.buildCancelFrame(), [0, HidDictationProtocol.flagCancel, 0]);
    });

    test('session ids never hit the reserved zero', () {
      // Mirrors the firmware rule: 0 is reserved. The controller's generator
      // is exercised in the controller test; here we assert the invariant the
      // protocol itself documents.
      expect(HidDictationProtocol.sessionNone, 0);
    });
  });

  group('HidDictationProtocol status parsing', () {
    test('parses all fields little-endian', () {
      final data = Uint8List(10);
      data[0] = 1; // version
      data[1] = HidDictationProtocol.stateTyping;
      data[2] = 1; // hidActive
      data[3] = 1; // hidPending
      data[4] = HidDictationProtocol.errUnsupportedChar;
      data[5] = 42; // errorDetail
      data[6] = 7; // activeSession
      data[7] = 6; // lastFinishedSession
      ByteData.view(data.buffer).setUint16(8, 513, Endian.little); // charsTyped

      final s = HidDictationProtocol.parseStatus(data)!;
      expect(s.version, 1);
      expect(s.state, HidDictationProtocol.stateTyping);
      expect(s.hidActive, isTrue);
      expect(s.hidPending, isTrue);
      expect(s.lastError, HidDictationProtocol.errUnsupportedChar);
      expect(s.errorDetail, 42);
      expect(s.activeSession, 7);
      expect(s.lastFinishedSession, 6);
      expect(s.charsTyped, 513);
      expect(s.isTyping, isTrue);
      expect(s.describe(), 'unsupported character at 42');
    });

    test('rejects short payloads', () {
      expect(HidDictationProtocol.parseStatus(Uint8List(9)), isNull);
      expect(HidDictationProtocol.parseStatus(Uint8List(0)), isNull);
    });
  });
}
