import 'package:collection/collection.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/constants.dart';

/// Recording transcript loading and display identity, independent of save/summary scheduling.
mixin ConversationRecordingSpeakers on ChangeNotifier {
  ServerConversation get conversation;
  ServerConversation? get conversationOrNull;
  ConversationProvider? get conversationProvider;
  bool get recordingSpeakersDisposed;
  bool get recordingAssignmentEnabled;
  Future<RecordingTranscript?> fetchRecordingTranscript(String id);

  RecordingTranscript? _recording;
  String? _recordingOwnerId;
  final Map<String, RecordingLine> _recordingById = {};
  List<TranscriptSegment>? _recordingSegments;
  List<TranscriptSegment>? _recordingDisplaySegments;
  List<TranscriptSegment> get recordingSegments => _recordingSegments ?? conversation.transcriptSegments;
  bool get hasRecordingSiblings => _recording?.lines.any((line) => line.conversationId != conversation.id) ?? false;
  int sourceSpeakerId(String id, int fallback) => _recordingById[id]?.segment.speakerId ?? fallback;

  /// Display ids group only proven voices; source ids remain untouched for persistence.
  List<TranscriptSegment> get recordingDisplaySegments {
    final displayed = _recordingDisplaySegments;
    if (displayed == null) return conversation.transcriptSegments;
    for (final line in displayed) {
      final original = _recordingById[line.id]!.segment;
      line.isUser = original.isUser;
      line.personId = original.personId;
      line.speakerLabelSource = original.speakerLabelSource;
    }
    return displayed;
  }

  bool loadingRecordingTranscript = false;
  bool recordingLoadFailed = false;
  bool recordingLoadLimited = false;
  bool get recordingCoverageComplete => _recording?.coverageComplete ?? false;
  bool speakerCoverageComplete = false;
  bool speakerAssignmentLimited = false;
  bool speakerAssignmentPartial = false;
  Future<void>? _recordingLoad;

  Future<void> loadRecordingTranscript() {
    if (_recordingOwnerId == conversation.id) return Future.value();
    if (_recordingLoad case final pending?) return pending;
    loadingRecordingTranscript = true;
    recordingLoadFailed = recordingLoadLimited = false;
    notifyListeners();
    final pending = _loadRecordingTranscript().whenComplete(() {
      _recordingLoad = null;
      loadingRecordingTranscript = false;
      if (!recordingSpeakersDisposed) notifyListeners();
    });
    _recordingLoad = pending;
    return pending;
  }

  Future<void> _loadRecordingTranscript() async {
    final id = conversation.id;
    if (_recordingOwnerId == id) return;
    RecordingTranscript? result;
    try {
      result = await fetchRecordingTranscript(id);
    } catch (error) {
      recordingLoadLimited = error is RecordingSpeakerLimitException;
      recordingLoadFailed = recordingAssignmentEnabled;
      return;
    }
    if (result == null) {
      recordingLoadFailed = recordingAssignmentEnabled;
      return;
    }
    if (recordingSpeakersDisposed || conversationOrNull?.id != id) return;
    final cached = <String, TranscriptSegment>{
      for (final cid in result.lines.map((line) => line.conversationId).toSet())
        for (final cachedLine
            in (conversationProvider?.loadedConversationById(cid)?.transcriptSegments ?? <TranscriptSegment>[]))
          '$cid/${cachedLine.id}': cachedLine,
    };
    final current = {for (final line in conversation.transcriptSegments) line.id: line};
    _recording = RecordingTranscript([
      for (final line in result.lines)
        RecordingLine(
            line.conversationId,
            line.conversationId == id
                ? (current[line.segment.id] ?? line.segment)
                : (cached['${line.conversationId}/${line.segment.id}'] ?? line.segment),
            scope: line.scope,
            label: line.label,
            offset: line.offset),
    ], episodeId: result.episodeId, enabled: result.enabled, coverage: result.coverage);
    final receivedIds = _recording!.lines.map((line) => line.segment.id).toSet();
    final pendingLines = current.values.where((line) => !receivedIds.contains(line.id)).toList();
    if (pendingLines.isNotEmpty) {
      final anchorOffset =
          _recording!.lines.where((line) => line.conversationId == id).map((line) => line.offset).firstOrNull ?? 0.0;
      _recording!.lines.addAll([for (final line in pendingLines) RecordingLine(id, line, offset: anchorOffset)]);
      _recording!.lines.sort((a, b) => (a.segment.start + a.offset).compareTo(b.segment.start + b.offset));
    }
    _recordingById.clear();
    _recordingById.addEntries(_recording!.lines.map((line) => MapEntry(line.segment.id, line)));
    _recordingSegments = _recording!.lines.map((line) => line.segment).toList();
    final displayIds = <Object, int>{};
    _recordingDisplaySegments = [
      for (final line in _recording!.lines)
        TranscriptSegment.fromJson(line.segment.toJson())
          ..start = line.segment.start + line.offset
          ..end = line.segment.end + line.offset
          ..speakerId = line.segment.speakerId == omiSpeakerId
              ? omiSpeakerId
              : displayIds.putIfAbsent(line.voice ?? (line.conversationId, line.segment.speakerId),
                  () => displayIds.length + 1 >= omiSpeakerId ? displayIds.length + 2 : displayIds.length + 1),
    ];
    _recordingOwnerId = id;
    notifyListeners();
  }

  List<TranscriptSegment> voiceSegmentsFor(String segmentId, int speakerId) {
    final row = _recordingById[segmentId];
    if (row == null) {
      final anchor = conversation.transcriptSegments.firstWhereOrNull((line) => line.id == segmentId);
      return conversation.transcriptSegments.where((line) => anchor?.sameRecordingVoice(line) ?? false).toList();
    }
    return _recording!.lines
        .where((line) => row.voice == null
            ? line.conversationId == row.conversationId && line.segment.speakerId == speakerId
            : line.voice == row.voice)
        .map((line) => line.segment)
        .toList();
  }

  Map<String, List<String>> recordingGroups(List<String> ids) {
    final groups = <String, List<String>>{};
    for (final id in ids) {
      final owner = _recordingById[id]?.conversationId ?? conversation.id;
      groups.putIfAbsent(owner, () => []).add(id);
    }
    return groups;
  }

  String recordingOwner(TranscriptSegment line) => _recordingById[line.id]?.conversationId ?? conversation.id;

  (String, String)? recordingVoiceFor(String? id) =>
      _recordingById[id]?.voice ?? recordingSegments.firstWhereOrNull((line) => line.id == id)?.recordingVoice;

  String? get recordingEpisodeId => _recording?.episodeId;
  RecordingLine? recordingLine(String? id) => _recordingById[id];
  void resetRecordingTranscript() {
    _recording = null;
    _recordingOwnerId = null;
    _recordingById.clear();
    _recordingSegments = null;
    _recordingDisplaySegments = null;
  }

  Future<ApiResult<int>> persistRecordingLabel(RecordingAssignmentCall assign, String conversationId,
      List<String> segmentIds, String personId, int? speakerId) async {
    speakerCoverageComplete = false;
    final result = await assign(
        conversationId,
        [
          for (final group in recordingGroups(segmentIds).entries)
            {
              'conversation_id': group.key,
              'segment_ids': group.value,
              if (speakerId != null) 'speaker_id': sourceSpeakerId(group.value.first, speakerId),
              if (speakerId != null && recordingVoiceFor(group.value.first) != null)
                'voice': {
                  'speaker_id_scope': recordingVoiceFor(group.value.first)!.$1,
                  'stream_speaker': recordingVoiceFor(group.value.first)!.$2,
                }
            },
        ],
        personId: personId,
        wholeRecording: speakerId != null,
        episodeId: recordingEpisodeId);
    speakerCoverageComplete = result is ApiSuccess<int> && !result.truncated;
    return result;
  }
}
