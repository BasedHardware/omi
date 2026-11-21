part of 'conversation_detail_provider.dart';

extension _ConversationSpeakerRestore on ConversationDetailProvider {
  Future<bool> _persistSpeakerRestore(
    ServerConversation target,
    Map<TranscriptSegment, (bool, String?, String?)> restore,
    Map<TranscriptSegment, (bool, String?, String?)> current,
    int generation,
    Future<void> previousSave,
  ) async {
    final landed = <TranscriptSegment>{};
    try {
      await previousSave;
      // One request per restored label: the lines an action covered may have carried different ones.
      final groups = <(bool, String?), List<TranscriptSegment>>{};
      for (final MapEntry(key: segment, value: original) in restore.entries) {
        groups.putIfAbsent((original.$1, original.$1 ? null : original.$2), () => []).add(segment);
      }
      for (final MapEntry(key: (isUser, personId), value: segments) in groups.entries) {
        final ids = [for (final segment in segments) segment.id];
        bool saved;
        try {
          saved = _assignRecording == null
              ? await _assignSpeaker(target.id, ids, isUser: isUser, personId: personId)
              : await persistRecordingLabel(_assignRecording!, target.id, ids, isUser ? 'user' : (personId ?? ''), null)
                  is ApiSuccess<int>;
        } on PartialSpeakerAssignmentException catch (error) {
          landed.addAll(segments.where((line) => error.succeeded.contains(recordingOwner(line))));
          saved = false;
        }
        if (!saved) {
          _rollForwardUnsavedRestore(target, restore, current, landed, generation);
          return false;
        }
        landed.addAll(segments);
      }
      if (_speakerConversationDeleted(target.id) || target.deleted) {
        _dropSpeakerRefreshState(target.id);
      } else if (target.status == ConversationStatus.completed && target.structured.overview.trim().isNotEmpty) {
        _automaticSpeakerSummaryRefreshIds.add(target.id);
        if (!_isDisposed && identical(conversationOrNull, target)) _speakerSummaryConversationId = target.id;
      }
      if (!_isDisposed && identical(conversationOrNull, target)) _notifySpeakerRestore();
      return true;
    } catch (_) {
      _rollForwardUnsavedRestore(target, restore, current, landed, generation);
      return false;
    } finally {
      await _finishSpeakerSave(target);
    }
  }

  /// A restore that failed part-way: the groups that already saved stay undone, the rest roll
  /// forward to the labels the server still has, so the transcript matches the server line by line.
  void _rollForwardUnsavedRestore(
    ServerConversation target,
    Map<TranscriptSegment, (bool, String?, String?)> restore,
    Map<TranscriptSegment, (bool, String?, String?)> current,
    Set<TranscriptSegment> landed,
    int generation,
  ) {
    final unsaved = [
      for (final segment in restore.keys)
        if (!landed.contains(segment)) segment,
    ];
    _rollbackSpeakerAssignment(target, unsaved, current, generation, null);
  }

  bool _speakerConversationDeleted(String conversationId) =>
      conversationProvider?.memoriesToDelete.containsKey(conversationId) == true ||
      (_cachedConversation?.id == conversationId && _cachedConversation?.deleted == true);
}
