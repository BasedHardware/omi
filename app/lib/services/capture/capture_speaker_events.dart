part of 'capture_controller.dart';

extension CaptureSpeakerEvents on CaptureController {
  void _handleSpeakerLabelSuggestionEvent(SpeakerLabelSuggestionEvent event) {
    if (_excludedSpeakers.contains(event.speakerId)) return;
    switch (reconcileSpeakerSuggestion(
      event,
      segments,
      taggingSegmentIds,
      suggestionsBySegmentId,
    )) {
      case SpeakerSuggestionDisposition.ignored:
        return;
      case SpeakerSuggestionDisposition.retained:
        _publishCaptureChange();
        return;
      case SpeakerSuggestionDisposition.assignment:
        break;
    }

    // Add backend-created person to local cache for UI display (backward compatibility)
    final isUser = event.personId == 'user';
    if (!isUser && event.personId.isNotEmpty && _preferences.getPersonById(event.personId) == null) {
      _preferences.addCachedPerson(
        Person(
          id: event.personId,
          name: event.personName,
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ),
      );
      _peopleRefreshFuture ??= externalActions.refreshPeople().whenComplete(() {
        _peopleRefreshFuture = null;
      }).catchError((Object error, StackTrace stack) {
        Logger.debug('People cache refresh failed: ${error.runtimeType}');
        return _reportDetachedCaptureError(
          'capture_people_refresh_suggestion',
          error,
          stack,
        );
      });
    }

    // Auto-apply assignment if backend provided personId (speaker_auto_assign=enabled)
    if (event.personId.isNotEmpty) {
      for (var seg in segments) {
        if (seg.speakerId == event.speakerId &&
            !seg.isUser &&
            seg.personId == null &&
            !taggingSegmentIds.contains(seg.id)) {
          seg.isUser = isUser;
          seg.personId = isUser ? null : event.personId;
        }
      }
      _segmentsPhotosVersion++; // Trigger UI rebuild after auto-apply
    }
    _publishCaptureChange();
  }
}
