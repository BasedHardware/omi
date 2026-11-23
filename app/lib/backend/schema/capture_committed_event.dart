import 'message_event.dart';

/// An exact transcript range with optional immutable audio evidence.
class CaptureCommittedEvent extends MessageEvent {
  final String conversationId, captureRoot, channel, clockEpoch;
  final String? recordingSessionId;
  final AudioCustodyEvent? audioCustody;
  final int sourceStart, sourceEnd;
  CaptureCommittedEvent({
    required String conversationId,
    required String captureRoot,
    required String channel,
    required String clockEpoch,
    String? recordingSessionId,
    required int sourceStart,
    required int sourceEnd,
  }) : this._(conversationId, captureRoot, channel, clockEpoch, recordingSessionId, sourceStart, sourceEnd, null);

  CaptureCommittedEvent._(
    this.conversationId,
    this.captureRoot,
    this.channel,
    this.clockEpoch,
    this.recordingSessionId,
    this.sourceStart,
    this.sourceEnd,
    this.audioCustody,
  ) : super(eventType: 'capture_committed');

  static MessageEvent parse(Map<String, dynamic> json) {
    final start = json['source_start'], end = json['source_end'];
    if (json['conversation_id'] is! String ||
        (json['conversation_id'] as String).isEmpty ||
        json['capture_root'] is! String ||
        (json['capture_root'] as String).isEmpty ||
        start is! int ||
        end is! int ||
        start < 0 ||
        end <= start ||
        json['channel'] != null && json['channel'] is! String ||
        json['clock_epoch'] != null && json['clock_epoch'] is! String ||
        json['recording_session_id'] != null && json['recording_session_id'] is! String) {
      return UnknownEvent(eventType: 'invalid_capture_committed');
    }
    final channel = json['channel'] as String? ?? 'default';
    final epoch = json['clock_epoch'] as String? ?? 'default';
    final binding = json['audio_custody'];
    final audio = binding is Map<String, dynamic> ? AudioCustodyEvent.parse(binding) : null;
    final bound = audio != null &&
        audio.conversationId == json['conversation_id'] &&
        audio.recordingSessionId == json['recording_session_id'] &&
        channel == 'mono' &&
        audio.frames.every((frame) =>
            frame.captureRoot == json['capture_root'] &&
            frame.clockEpoch.toString() == epoch &&
            frame.ordinal >= start &&
            frame.ordinal < end);
    return CaptureCommittedEvent._(
      json['conversation_id'],
      json['capture_root'],
      channel,
      epoch,
      json['recording_session_id'],
      start,
      end,
      bound ? audio : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'type': eventType,
        'conversation_id': conversationId,
        'capture_root': captureRoot,
        'channel': channel,
        'clock_epoch': clockEpoch,
        'recording_session_id': recordingSessionId,
        'source_start': sourceStart,
        'source_end': sourceEnd,
        if (audioCustody != null) 'audio_custody': audioCustody!.toJson(),
      };
}
