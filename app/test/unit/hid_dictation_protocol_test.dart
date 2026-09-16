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

    test('default payload is MTU-23-safe and chunks long text', () {
      expect(HidDictationProtocol.maxFramePayload, 17);
      final text = 'a' * 40; // 17 + 17 + 6 at the conservative default
      final frames = HidDictationProtocol.buildFrames(9, text);
      expect(frames, hasLength(3));
      expect(frames[0][2], 17);
      expect(frames[1][2], 17);
      expect(frames[2][2], 6);
      expect(frames[0][1], 0x00);
      expect(frames[1][1], 0x00);
      expect(frames[2][1], HidDictationProtocol.flagFinal);
      expect(frames.map((f) => String.fromCharCodes(f.sublist(3))).join(), text);
    });

    test('fails closed on bad input instead of silently filtering', () {
      expect(() => HidDictationProtocol.buildFrames(0, 'ok'), throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(256, 'ok'), throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(1, 'ok\n'), throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(1, 'é'), throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(1, 'a' * (HidDictationProtocol.maxTextLength + 1)),
          throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(1, 'ok', maxPayload: 245), throwsArgumentError);
      expect(() => HidDictationProtocol.buildFrames(1, 'ok', maxPayload: 0), throwsArgumentError);
    });

    test('cancel frames are well-formed', () {
      expect(HidDictationProtocol.buildCancelFrame(3), [3, HidDictationProtocol.flagCancel, 0]);
      expect(HidDictationProtocol.buildCancelFrame(), [0, HidDictationProtocol.flagCancel, 0]);
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

    test('fails closed on short payloads and unknown versions', () {
      expect(HidDictationProtocol.parseStatus(Uint8List(9)), isNull);
      expect(HidDictationProtocol.parseStatus(Uint8List(0)), isNull);
      final future = Uint8List(10);
      future[0] = 2; // a protocol this build does not speak
      expect(HidDictationProtocol.parseStatus(future), isNull);
    });
  });
}
