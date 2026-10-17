part of 'name_speaker_sheet.dart';

extension _NativeSpeakerPresentation on _NameSpeakerBottomSheetState {
  Widget _nativeSpeakerSurface(Widget classic, List<Person> people, String userName) {
    if (!iosSwiftUiEnabled) return classic;
    final l10n = context.l10n;
    final current = widget.segments.firstWhereOrNull((s) => s.id == widget.segmentId);
    final person = people.firstWhereOrNull((p) => p.id == current?.personId);
    final choices = [
      Person(id: 'user', name: l10n.you, createdAt: DateTime.now(), updatedAt: DateTime.now()),
      ...people.where((p) => p.id != _rejectedPersonId),
    ]..sort((a, b) => _NameSpeakerBottomSheetState._comparePeopleForPicker(a, b,
        currentPersonId: current?.personId,
        suggestionId: widget.suggestion?.personId,
        lastUsedMs: SharedPreferencesUtil().speakerLabelLastUsedMs,
        frequencies: _personFrequencies()));
    final others = widget.segments.where((s) => s.speakerId == widget.speakerId && s.id != widget.segmentId).toList();
    return IosNativeSurface(title: l10n.nameSpeakerTitle, fallback: classic, loading: loading, toolbar: [
      NativeRow('speaker_close', l10n.close,
          symbol: 'xmark', enabled: !loading, action: (_) => Navigator.of(context).maybePop()),
      NativeRow('speaker_save', l10n.save,
          symbol: 'checkmark', enabled: allowSave && !loading, action: (_) => _saveSpeaker()),
    ], sections: [
      NativeSection('speaker_picker', [
        if (speakerTextSample != null) NativeRow('speaker_sample', speakerTextSample!, kind: 'label'),
        if (_isCreatingNewPerson) ...[
          NativeRow('speaker_new_name', l10n.enterPersonsName,
              kind: 'text',
              value: _controller.text,
              enabled: !loading,
              action: (value) => _nativeRebuild(() {
                    _controller.text = value as String;
                    _validateNewPersonName(value, people, userName);
                  })),
          if (_duplicateNameError != null) NativeRow('speaker_name_error', _duplicateNameError!, kind: 'label'),
          NativeRow('speaker_new_cancel', l10n.cancel,
              enabled: !loading,
              action: (_) => _nativeRebuild(() {
                    _isCreatingNewPerson = false;
                    _controller.clear();
                    setAllowSave(selectedPerson.isNotEmpty);
                  })),
        ] else ...[
          NativeRow('speaker_person', l10n.nameSpeakerTitle,
              kind: 'choice',
              value: selectedPerson.isEmpty ? '__no_selection__' : selectedPerson,
              enabled: !loading,
              optionSearch: l10n.search,
              optionClose: l10n.close,
              options: {
                '__no_selection__': l10n.nameSpeakerTitle,
                for (final person in choices) person.id: person.name
              }, action: (value) {
            final person = choices.firstWhereOrNull((p) => p.id == value);
            if (person == null) return;
            setSelectedPerson(person.id);
            setSelectedPersonName(person.name);
          }),
          NativeRow('speaker_add_person', l10n.addPerson,
              symbol: 'person.badge.plus',
              enabled: !loading,
              action: (_) => _startCreatePersonWithName('', people, userName)),
          if (widget.onSpeakerRejected != null) ...[
            if (current?.isUser == true)
              NativeRow('speaker_not_me', l10n.speakerTagPromptNotMeAction,
                  enabled: !loading, action: (_) => _reject(SpeakerRejection.notMe)),
            if (person != null)
              NativeRow('speaker_not_person', l10n.speakerLabelText('notPerson', person.name),
                  enabled: !loading, action: (_) => _reject(SpeakerRejection.notPerson)),
            NativeRow('speaker_not_a_person', l10n.speakerTagPromptNotAPerson,
                enabled: !loading, action: (_) => _reject(SpeakerRejection.notAPerson)),
          ],
        ],
        NativeRow('speaker_apply', l10n.tagSpeakerIncludingLaterSpeech,
            kind: 'toggle',
            value: _applyToSpeaker,
            enabled: !loading,
            action: (value) => _nativeRebuild(() {
                  _applyToSpeaker = value as bool;
                  _isSegmentsExpanded = _applyToSpeaker && others.isNotEmpty;
                  if (_applyToSpeaker) {
                    _selectedSegmentIds = {..._selectedSegmentIds, ...others.map((s) => s.id)}.toList();
                  } else {
                    final ids = others.map((s) => s.id).toSet();
                    _selectedSegmentIds.removeWhere(ids.contains);
                  }
                })),
        NativeRow('speaker_manage', l10n.managePeople,
            symbol: 'person.2', enabled: !loading, action: (_) => routeToPage(context, const UserPeoplePage())),
        if (_isSegmentsExpanded)
          for (final segment in others)
            NativeRow('speaker_line:${segment.id}', segment.text,
                kind: 'toggle',
                subtitle: OmiDuration.offset(segment.start),
                value: _selectedSegmentIds.contains(segment.id),
                enabled: !loading,
                action: (value) => _nativeRebuild(() {
                      if (value == true) {
                        if (!_selectedSegmentIds.contains(segment.id)) _selectedSegmentIds.add(segment.id);
                      } else {
                        _selectedSegmentIds.remove(segment.id);
                        _applyToSpeaker = false;
                      }
                    })),
        if (_saveFailed) NativeRow('speaker_error', l10n.somethingWentWrong, kind: 'label'),
      ])
    ]);
  }
}
