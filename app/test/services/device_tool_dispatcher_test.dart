import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/device_tools/device_tool_dispatcher.dart';

void main() {
  group('DeviceToolRequest.tryParse', () {
    test('parses a well-formed request', () {
      final request = DeviceToolRequest.tryParse(jsonEncode({
        'call_id': 'abc-123',
        'tool': 'propose_message',
        'arguments': {
          'to': ['+15550100'],
          'text': 'running late',
        },
      }));

      expect(request, isNotNull);
      expect(request!.callId, 'abc-123');
      expect(request.tool, 'propose_message');
      expect(request.arguments['to'], ['+15550100']);
      expect(request.arguments['text'], 'running late');
    });

    test('treats missing arguments as empty rather than failing', () {
      final request = DeviceToolRequest.tryParse(jsonEncode({
        'call_id': 'abc-123',
        'tool': 'search_contacts',
      }));

      expect(request, isNotNull);
      expect(request!.arguments, isEmpty);
    });

    test('rejects a frame with no call_id', () {
      final raw = jsonEncode({'tool': 'propose_message', 'arguments': {}});

      expect(DeviceToolRequest.tryParse(raw), isNull);
    });

    test('rejects a frame with an empty tool name', () {
      final raw = jsonEncode({'call_id': 'abc', 'tool': '', 'arguments': {}});

      expect(DeviceToolRequest.tryParse(raw), isNull);
    });

    test('rejects malformed JSON instead of throwing', () {
      expect(DeviceToolRequest.tryParse('{not json'), isNull);
    });

    test('rejects a non-object payload', () {
      expect(DeviceToolRequest.tryParse('[1,2,3]'), isNull);
    });

    test('survives a body containing JSON and newlines', () {
      // Message bodies are user text; the base64 SSE frame must round-trip them
      // without the payload being reinterpreted as protocol.
      const body = 'hey {"call_id":"spoofed"}\nsecond line "quoted"';
      final request = DeviceToolRequest.tryParse(jsonEncode({
        'call_id': 'real-call',
        'tool': 'propose_message',
        'arguments': {
          'to': ['+15550100'],
          'text': body,
        },
      }));

      expect(request!.callId, 'real-call');
      expect(request.arguments['text'], body);
    });
  });

  group('DeviceToolRequest.recoverCallId', () {
    test('recovers the call id from a frame too damaged to execute', () {
      // The server is blocked on this id. Refusing to run the call is right;
      // refusing to answer it makes the user wait out the whole timeout.
      final raw = jsonEncode({'call_id': 'abc-123', 'tool': ''});

      expect(DeviceToolRequest.tryParse(raw), isNull);
      expect(DeviceToolRequest.recoverCallId(raw), 'abc-123');
    });

    test('returns null when there is no id to answer', () {
      expect(DeviceToolRequest.recoverCallId('{not json'), isNull);
      expect(DeviceToolRequest.recoverCallId(jsonEncode({'tool': 'propose_message'})), isNull);
    });
  });
}
