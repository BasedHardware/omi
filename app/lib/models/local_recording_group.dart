import 'package:omi/models/local_recording.dart';

/// Home projects recovery files into their original Watch session. The files
/// remain independent custody objects; grouping never joins or processes audio.
class LocalRecordingGroup {
  final String id;
  final String? watchSessionId;
  final List<LocalRecording> recordings;
  final int seconds;

  LocalRecordingGroup._(this.id, this.watchSessionId, List<LocalRecording> recordings)
      : recordings = List.unmodifiable(recordings),
        seconds = recordings.fold(0, (total, recording) => total + recording.seconds);

  bool get isWatchRecovery => watchSessionId != null;
  DateTime get startedAt => recordings.first.startedAt;
  int get timerStart => recordings.first.timerStart;
}

/// Group before date bucketing so a session crossing midnight has one Home row.
/// Only the explicit session ID in a validated Watch filename can join files;
/// phone recordings, unknown names and distinct Watch sessions stay separate.
List<LocalRecordingGroup> groupLocalRecordings(List<LocalRecording> recordings) {
  final groups = <String, List<LocalRecording>>{};
  final sessions = <String, String?>{};
  for (final recording in recordings) {
    final session = watchRecordingSessionId(recording.fileName);
    final id = session == null ? recording.id : 'watch_$session';
    (groups[id] ??= []).add(recording);
    sessions[id] = session;
  }
  final result = <LocalRecordingGroup>[];
  for (final entry in groups.entries) {
    entry.value.sort((a, b) {
      final time = a.timerStart.compareTo(b.timerStart);
      return time == 0 ? a.fileName.compareTo(b.fileName) : time;
    });
    result.add(LocalRecordingGroup._(entry.key, sessions[entry.key], entry.value));
  }
  result.sort((a, b) => b.timerStart.compareTo(a.timerStart));
  return result;
}

final _watchRecordingName = RegExp(r'^audio_omibatchwatch([0-9a-fA-F]{32})s\d+_pcm16_16000_1_fs160_\d+\.bin$');

String? watchRecordingSessionId(String fileName) => _watchRecordingName.firstMatch(fileName)?.group(1)?.toLowerCase();
