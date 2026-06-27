import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

/// Tests the SSE parser logic used in makeStreamingApiCall (shared.dart).
///
/// The production code accumulates a remainder across TCP reads and only
/// emits complete events delimited by \n\n.  These tests verify the parser
/// handles arbitrary TCP fragmentation correctly.

/// Pure reimplementation of the SSE parser from shared.dart for unit testing.
/// Mirrors the exact logic so tests validate behavior without needing
/// HttpPoolManager, auth, or network.
Stream<String> parseSseStream(Stream<String> rawStream) async* {
  var remainder = '';
  await for (var data in rawStream) {
    remainder += data;
    var parts = remainder.split('\n\n');
    remainder = parts.removeLast();
    for (var part in parts) {
      if (part.isNotEmpty) {
        yield part;
      }
    }
  }

  if (remainder.isNotEmpty) {
    yield remainder;
  }
}

void main() {
  group('SSE parser — complete events', () {
    test('single complete event', () async {
      final stream = Stream.fromIterable(['data: hello\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: hello']);
    });

    test('two complete events in one read', () async {
      final stream = Stream.fromIterable(['data: a\n\ndata: b\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: a', 'data: b']);
    });

    test('empty lines between events are skipped', () async {
      final stream = Stream.fromIterable(['data: a\n\n\n\ndata: b\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: a', 'data: b']);
    });
  });

  group('SSE parser — TCP fragmentation', () {
    test('event split across two reads', () async {
      final stream = Stream.fromIterable(['data: hel', 'lo\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: hello']);
    });

    test('prefix split across reads (da + ta: hello)', () async {
      final stream = Stream.fromIterable(['da', 'ta: hello\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: hello']);
    });

    test('delimiter split across reads', () async {
      final stream = Stream.fromIterable(['data: hello\n', '\ndata: world\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: hello', 'data: world']);
    });

    test('many small fragments', () async {
      // Simulate 10-byte TCP fragments for "data: hello world\n\n"
      final full = 'data: hello world\n\n';
      final fragments = <String>[];
      for (var i = 0; i < full.length; i += 5) {
        fragments.add(full.substring(i, i + 5 > full.length ? full.length : i + 5));
      }
      final stream = Stream.fromIterable(fragments);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: hello world']);
    });

    test('two events plus partial third', () async {
      final stream = Stream.fromIterable(['data: a\n\ndata: b\n\ndata: part', 'ial\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: a', 'data: b', 'data: partial']);
    });

    test('large event (> 1024 bytes) arrives in fragments', () async {
      final payload = 'x' * 2000;
      final full = 'data: $payload\n\n';
      // Split into ~80 byte fragments like our TCP proxy
      final fragments = <String>[];
      for (var i = 0; i < full.length; i += 80) {
        fragments.add(full.substring(i, i + 80 > full.length ? full.length : i + 80));
      }
      final stream = Stream.fromIterable(fragments);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: $payload']);
    });
  });

  group('SSE parser — done/message base64 events', () {
    test('done event with base64 payload', () async {
      final b64 = base64Encode(utf8.encode('{"id":"123","text":"hi"}'));
      final stream = Stream.fromIterable(['done: $b64\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events.length, 1);
      expect(events[0], startsWith('done: '));
    });

    test('done event base64 split across fragments', () async {
      final b64 = base64Encode(utf8.encode('{"id":"msg-1","text":"hello world"}'));
      final full = 'done: $b64\n\n';
      final mid = full.length ~/ 2;
      final stream = Stream.fromIterable([full.substring(0, mid), full.substring(mid)]);
      final events = await parseSseStream(stream).toList();
      expect(events, ['done: $b64']);
    });
  });

  group('SSE parser — edge cases', () {
    test('trailing data without delimiter is flushed', () async {
      final stream = Stream.fromIterable(['data: no-terminator']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['data: no-terminator']);
    });

    test('empty stream produces no events', () async {
      final stream = Stream<String>.empty();
      final events = await parseSseStream(stream).toList();
      expect(events, isEmpty);
    });

    test('only delimiters produce no events', () async {
      final stream = Stream.fromIterable(['\n\n\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, isEmpty);
    });

    test('think prefix handled correctly', () async {
      final stream = Stream.fromIterable(['think: reasoning here\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['think: reasoning here']);
    });

    test('mixed event types', () async {
      final stream = Stream.fromIterable(['think: step1\n\ndata: result\n\ndone: abc\n\n']);
      final events = await parseSseStream(stream).toList();
      expect(events, ['think: step1', 'data: result', 'done: abc']);
    });
  });
}
