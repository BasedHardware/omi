import 'message_event.dart';

/// Exact source-frame custody receipt, never wall-clock or text coverage.
class CaptureCommittedEvent extends MessageEvent {
  final String conversationId, captureRoot, channel, clockEpoch;
  final String? recordingSessionId;
  final int sourceStart, sourceEnd;
  CaptureCommittedEvent(
      {required this.conversationId,
      required this.captureRoot,
      required this.channel,
      required this.clockEpoch,
      this.recordingSessionId,
      required this.sourceStart,
      required this.sourceEnd})
      : super(eventType: 'capture_committed');

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
    return CaptureCommittedEvent(
        conversationId: json['conversation_id'],
        captureRoot: json['capture_root'],
        channel: json['channel'] ?? 'default',
        clockEpoch: json['clock_epoch'] ?? 'default',
        recordingSessionId: json['recording_session_id'],
        sourceStart: start,
        sourceEnd: end);
  }

  Map<String, dynamic> toJson() => {
        'type': eventType,
        'conversation_id': conversationId,
        'capture_root': captureRoot,
        'channel': channel,
        'clock_epoch': clockEpoch,
        'recording_session_id': recordingSessionId,
        'source_start': sourceStart,
        'source_end': sourceEnd
      };
}
