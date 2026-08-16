import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/gen/audio_wire.g.dart' as wire;

AudioUrlsResponse _parse(Map<String, dynamic> json) {
  return AudioUrlsResponse.fromGenerated(wire.GeneratedAudioUrlsResponse.fromJson(json));
}

void main() {
  const cachedPart = {
    'id': 'A',
    'status': 'cached',
    'signed_url': 'https://part-a',
    'content_type': 'audio/mpeg',
    'duration': 10.0,
  };
  const pendingPart = {'id': 'B', 'status': 'pending', 'signed_url': null, 'duration': 5.0};

  const conversationAudioJson = {
    'status': 'cached',
    'signed_url': 'https://conv-mp3',
    'content_type': 'audio/mpeg',
    'duration': 215.0,
    'captured_duration': 15.0,
    'spans': [
      {'file_id': 'A', 'wall_offset': 10.0, 'artifact_offset': 0.0, 'len': 10.0},
      {'file_id': 'B', 'wall_offset': 210.0, 'artifact_offset': 10.0, 'len': 5.0},
    ],
  };

  group('AudioUrlsResponse parsing', () {
    test('parses conversation_audio with spans', () {
      final response = _parse(const {
        'audio_files': [cachedPart],
        'conversation_audio': conversationAudioJson,
        'poll_after_ms': null,
      });

      final ca = response.conversationAudio!;
      expect(ca.isCached, isTrue);
      expect(ca.signedUrl, 'https://conv-mp3');
      expect(ca.duration, 215.0);
      expect(ca.capturedDuration, 15.0);
      expect(ca.spans.length, 2);
      expect(ca.spans[1].wallOffset, 210.0);
      expect(ca.spans[1].artifactOffset, 10.0);
    });

    test('old backend response without conversation_audio parses to null', () {
      final response = _parse(const {
        'audio_files': [cachedPart],
      });
      expect(response.conversationAudio, isNull);
      expect(response.files.length, 1);
    });
  });

  group('playbackReady', () {
    test('true when the conversation artifact is cached even with pending parts', () {
      final response = _parse(const {
        'audio_files': [pendingPart],
        'conversation_audio': conversationAudioJson,
        'poll_after_ms': 3000,
      });
      expect(response.hasPending, isTrue);
      expect(response.playbackReady, isTrue);
    });

    test('true when all parts are ready and no conversation artifact exists', () {
      final response = _parse(const {
        'audio_files': [cachedPart],
      });
      expect(response.playbackReady, isTrue);
    });

    test('false when parts are pending and the conversation artifact is too', () {
      final response = _parse(const {
        'audio_files': [pendingPart],
        'conversation_audio': {'status': 'pending', 'signed_url': null, 'spans': []},
        'poll_after_ms': 3000,
      });
      expect(response.playbackReady, isFalse);
    });

    test('unavailable everywhere is terminal, not pending', () {
      final response = _parse(const {
        'audio_files': [
          {'id': 'A', 'status': 'unavailable', 'signed_url': null, 'duration': 1.0},
        ],
        'conversation_audio': {'status': 'unavailable', 'signed_url': null, 'spans': []},
      });
      expect(response.hasPending, isFalse);
      expect(response.playbackReady, isTrue);
      expect(response.conversationAudio!.isCached, isFalse);
    });
  });
}
