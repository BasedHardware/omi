part of 'capture_controller.dart';

extension CaptureSpeakerEvents on CaptureController {
  void _handleSpeakerLabelSuggestionEvent(SpeakerLabelSuggestionEvent event) {
    final serving = ClientRefactorFlags.serving;
    ClientRefactorFlags.compare('speaker_owner', event.resolvesOwner == (event.personId == 'user'));
    switch (reconcileSpeakerSuggestion(event, segments, taggingSegmentIds, suggestionsBySegmentId,
        explicitOwner: serving)) {
      case SpeakerSuggestionDisposition.reverted:
        _segmentsPhotosVersion++;
        _publishCaptureChange();
        return;
      case SpeakerSuggestionDisposition.ignored:
        return;
      case SpeakerSuggestionDisposition.retained:
        _publishCaptureChange();
        return;
      case SpeakerSuggestionDisposition.assignment:
        break;
    }

    // Add backend-created person to local cache for UI display (backward compatibility)
    final isUser = serving ? event.resolvesOwner : event.personId == 'user';
    if (!isUser && event.personId.isNotEmpty && _preferences.getPersonById(event.personId) == null) {
      _preferences.addCachedPerson(
        Person(id: event.personId, name: event.personName, createdAt: DateTime.now(), updatedAt: DateTime.now()),
      );
      _peopleRefreshFuture ??= externalActions.refreshPeople().whenComplete(() {
        _peopleRefreshFuture = null;
      }).catchError((Object error, StackTrace stack) {
        Logger.debug('People cache refresh failed: ${error.runtimeType}');
        return _reportDetachedCaptureError('capture_people_refresh_suggestion', error, stack);
      });
    }

    // Auto-apply assignment if backend provided personId (speaker_auto_assign=enabled)
    if (serving) {
      applyResolvedSpeakerSuggestion(event, segments, taggingSegmentIds);
      _segmentsPhotosVersion++;
      // refactor: superseded by speaker_suggestions when clients_refactor=serve
    } else if (event.personId.isNotEmpty) {
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
