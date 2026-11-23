import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/backend/schema/message_event.dart';

const _root = '11111111-2222-4333-8444-555555555555';
const _otherRoot = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

Map<String, dynamic> _listenWire() =>
    jsonDecode(File('test/fixtures/listen_audio_custody.json').readAsStringSync()) as Map<String, dynamic>;

Map<String, dynamic> _transcriptWire() => {
      'type': 'capture_committed',
      'conversation_id': 'conversation',
      'capture_root': _root,
      'channel': 'mono',
      'clock_epoch': '2',
      'recording_session_id': 'recording',
      'source_start': 7,
      'source_end': 9,
    };

void main() {
  test('Listen original and manifest receipt round trips for journal replay', () {
    final wire = _listenWire();
    final event = MessageEvent.fromJson(wire) as AudioCustodyEvent;
    expect(event.frames.map((frame) => (frame.captureRoot, frame.channel, frame.clockEpoch, frame.ordinal)), [
      (_root, 'mono', 2, 7),
      (_otherRoot, 'mono', 2, 8),
      (_root, 'mono', 2, 9),
    ]);
    expect(event.frames.first.sha256, (wire['frames'] as List).first['sha256']);
    expect(event.owner, 'owner');
    expect(event.recordingSessionId, 'recording');
    expect(event.toJson(), wire);
    final replay = AudioCustodyEvent.parse(jsonDecode(jsonEncode(event.toJson())) as Map<String, dynamic>);
    expect(replay?.toJson(), wire);
    (wire['receipt'] as Map)['generation'] = '99';
    expect((event.toJson()['receipt'] as Map)['generation'], '17');
  });

  test('accepts the media-addressed path of a framed encrypted manifest', () {
    final wire = _listenWire();
    final receipt = wire['receipt'] as Map<String, dynamic>;
    receipt['path'] = '${receipt['path']}.enc';
    receipt['manifest_path'] = (receipt['path'] as String).replaceFirst('raw-live/', 'audio-outbox/');
    expect(AudioCustodyEvent.parse(wire)?.toJson(), wire);
  });

  test('rejects malformed pins, channel and claimed frame identity', () {
    final mutations = <void Function(Map<String, dynamic>)>[
      (wire) => wire['channel'] = '1',
      (wire) => wire['channel'] = 0,
      (wire) => wire['recording_session_id'] = '',
      (wire) => wire['receipt']['generation'] = '0',
      (wire) => wire['receipt']['manifest_generation'] = 17,
      (wire) => wire['receipt']['sha256'] = List.filled(64, '0').join(),
      (wire) => wire['receipt']['manifest_sha256'] = 'bad',
      (wire) => wire['receipt']['manifest_path'] = wire['receipt']['path'],
      (wire) => wire['frames'][0]['sha256'] = null,
      (wire) => wire['frames'][0]['source']['clock_epoch'] = '2',
      (wire) => wire['frames'][0]['source']['source_frame'] = -1,
      (wire) => wire['frames'] = [wire['frames'][1]],
    ];
    for (final mutate in mutations) {
      final wire = _listenWire();
      mutate(wire);
      expect(AudioCustodyEvent.parse(wire), isNull);
      expect(MessageEvent.fromJson(wire), isA<UnknownEvent>());
    }
  });

  test('transcript-only range supplies no audio custody', () {
    final wire = _transcriptWire();
    final event = MessageEvent.fromJson(wire) as CaptureCommittedEvent;
    expect(event.audioCustody, isNull);
    expect(event.toJson(), wire);
  });

  test('explicit binding requires the same conversation, session and named source range', () {
    final transcript = _transcriptWire();
    final custody = _listenWire();
    final rows = custody['frames'] as List;
    custody['frames'] = [rows.first];
    custody['recording_session_id'] = 'recording';
    transcript['audio_custody'] = custody;
    CaptureCommittedEvent parse() => MessageEvent.fromJson(transcript) as CaptureCommittedEvent;

    expect(parse().audioCustody?.frames.single.ordinal, 7);
    expect(parse().toJson(), transcript);
    custody['frames'] = [rows.first, rows.last]; // Ordinal 9 is outside [7, 9).
    expect(parse().audioCustody, isNull);
    custody['frames'] = [rows[2]]; // Ordinal 8 belongs to a different source root.
    expect(parse().audioCustody, isNull);
    custody['frames'] = [rows.first];
    custody['recording_session_id'] = 'other-recording';
    expect(parse().audioCustody, isNull);
    custody['recording_session_id'] = 'recording';
    transcript['conversation_id'] = 'other-conversation';
    expect(parse().audioCustody, isNull);
    transcript['conversation_id'] = 'conversation';
    transcript['clock_epoch'] = '3';
    expect(parse().audioCustody, isNull);
  });
}
