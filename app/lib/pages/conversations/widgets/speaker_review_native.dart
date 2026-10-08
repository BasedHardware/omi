import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/widgets/speaker_tag_prompt_card.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The meter level a native row may carry (0..3); anything else draws no meter.
int? _nativeLevel(int? level) => level?.clamp(0, 3);

/// What the Flutter chip announces beside the name: pinned, and the voice-match level. The native
/// meter is decorative, so the row says it in words.
String _nativeMatchDescription(BuildContext context, GeneratedSpeakerTagCandidate candidate) => [
      if (candidate.pinned) context.l10n.peopleFilterPinned,
      if (candidate.matchLevel != null)
        context.l10n.voiceMatchMeterLabel(voiceMatchLabel(context, candidate.matchLevel!.clamp(1, 3))),
    ].join(', ');

/// The longest literal text a native label carries; longer server text is shortened.
String _nativeText(String text, [int limit = 500]) {
  final characters = text.characters;
  return characters.length <= limit ? text : '${characters.take(limit - 1)}…';
}

/// "Help Omi recognize voices" as a native sheet. [SpeakerTagPromptsProvider] and [PeopleProvider]
/// stay the owners: every row calls the same provider methods as [SpeakerTagPromptCard], which is
/// the complete fallback. Only the clip's 40 bar levels cross the bridge, never its audio.
class NativeSpeakerReview extends StatefulWidget {
  const NativeSpeakerReview({super.key});

  @override
  State<NativeSpeakerReview> createState() => _NativeSpeakerReviewState();
}

class _NativeSpeakerReviewState extends State<NativeSpeakerReview> {
  bool _shown = false;
  bool _closing = false;
  Uint8List? _waveSource;
  List<double> _waveLevels = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<SpeakerTagPromptsProvider>().loadIfDue();
    });
  }

  /// Pops this sheet only while it is the top route, never a picker or modal opened above it.
  void _pop() {
    if (_closing || !mounted || ModalRoute.of(context)?.isCurrent != true) return;
    _closing = true;
    Navigator.of(context).pop();
  }

  void _close(SpeakerTagPromptsProvider provider) {
    unawaited(provider.close());
    _pop();
  }

  /// The bars of [wav], derived once per clip.
  List<double> _levels(Uint8List wav) {
    if (!identical(wav, _waveSource)) {
      _waveSource = wav;
      _waveLevels = waveformLevels(wav, bars: 40);
    }
    return _waveLevels;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<SpeakerTagPromptsProvider>();
    final people = context.watch<PeopleProvider?>()?.people ?? const <Person>[];
    final visible = provider.visible && (provider.finished || provider.current != null);
    // The set closed or ran out of clips: the sheet has nothing left to show.
    if (visible) {
      _shown = true;
    } else if (_shown) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _pop());
    }
    final sections = <NativeSection>[
      if (visible) ...[
        NativeSection('speaker_review_top', [
          NativeRow('speaker_review_header', l10n.speakerTagPromptTitle,
              kind: 'label',
              symbol: 'person.wave.2',
              subtitle: provider.prompts.length > 1 && !provider.finished
                  ? l10n.speakerTagPromptProgress(
                      math.min(provider.index + 1, provider.prompts.length), provider.prompts.length)
                  : '',
              onVisible: (_) => provider.reportShown()),
        ]),
        if (provider.finished)
          NativeSection('speaker_review_done', [
            NativeRow('speaker_review_finished', l10n.speakerTagPromptThanks,
                kind: 'label', symbol: 'checkmark.circle.fill'),
            NativeRow('speaker_review_done_button', l10n.done, action: (_) => _close(provider)),
          ])
        else if (provider.pending != null)
          NativeSection('speaker_review_answer', [_answered(context, provider.pending!, people)])
        else
          ..._question(context, provider, provider.current!, people),
        if (provider.firstTime)
          NativeSection('speaker_review_settings', [
            NativeRow('speaker_review_save_voices', l10n.speakerTagPromptSaveVoicesTitle,
                kind: 'toggle',
                subtitle: l10n.speakerTagPromptSaveVoicesBody,
                value: provider.saveOtherVoiceProfiles,
                action: (value) => provider.setSaveOtherVoiceProfiles(value as bool, fromFirstPrompt: true)),
          ]),
      ],
    ];
    return IosNativeSurface(
      title: l10n.speakerTagPromptTitle,
      toolbar: [NativeRow('speaker_review_close', l10n.close, symbol: 'xmark', action: (_) => _close(provider))],
      sections: sections,
      fallback: OmiSheetScaffold(title: l10n.speakerTagPromptTitle, child: const SpeakerTagPromptCard()),
    );
  }

  /// The answer during its Undo window and just after it commits, with that person's meter.
  NativeRow _answered(BuildContext context, PendingSpeakerTagAnswer pending, List<Person> people) {
    final l10n = context.l10n;
    final person = people.firstWhereOrNull((p) => p.id == pending.personId);
    final (String symbol, String text) = switch (pending.answer) {
      SpeakerTagAnswer.me => ('person', l10n.speakerTagPromptSavedAsYou),
      SpeakerTagAnswer.notAPerson => ('tv', l10n.speakerTagPromptIgnoredNote),
      _ when pending.displayName != null => ('person', l10n.speakerTagPromptSavedAs(pending.displayName!)),
      _ => ('person.slash', l10n.speakerTagPromptRejectedToast),
    };
    return NativeRow('speaker_review_answered', text,
        kind: 'label',
        subtitle: person == null ? '' : confidenceLabel(context, person.confidence),
        level: person == null ? null : confidenceLevel(person.confidence),
        symbol: pending.committed ? 'checkmark.circle.fill' : symbol);
  }

  List<NativeSection> _question(
      BuildContext context, SpeakerTagPromptsProvider provider, GeneratedSpeakerTagPrompt prompt, List<Person> people) {
    final l10n = context.l10n;
    final candidates = speakerTagCandidates(prompt, people);
    final enabled = !provider.submitting;
    final suggested = people.firstWhereOrNull((p) => p.id == prompt.suggestedPersonId);
    final suggestedName = prompt.suggestedPersonName ?? suggested?.name;
    // Commands resolve against the prompt this projection showed; a later prompt ignores them.
    void give(SpeakerTagAnswer answer, {String? personId, String? name, String? displayName}) {
      // A staged answer is still in its Undo window: a second tap before the answered snapshot
      // arrives would otherwise drop it.
      if (!mounted || provider.submitting || provider.pending != null || provider.current?.id != prompt.id) return;
      unawaited(
          giveSpeakerTagAnswer(context, provider, answer, personId: personId, name: name, displayName: displayName));
    }

    void candidate(int index) {
      if (index < 0 || index >= candidates.length) return;
      final picked = candidates[index];
      give(SpeakerTagAnswer.person, personId: picked.personId, displayName: picked.name);
    }

    final playing = provider.playingPromptId == prompt.id;
    final started = prompt.conversationStartedAt?.toLocal();
    final seconds = math.max(0, (prompt.clipEnd - prompt.clipStart).round());
    final wav = provider.clipFor(prompt.id);
    final levels = wav == null ? const <double>[] : _levels(wav);
    final meta = [
      if (prompt.conversationTitle.isNotEmpty) prompt.conversationTitle,
      if (started != null) OmiDateFormat.of(context).timestamp(started),
    ].join(' · ');
    final question = switch (prompt.kind) {
      'confirm_person' when suggestedName != null && suggestedName.isNotEmpty =>
        l10n.speakerTagPromptIsThisPerson(suggestedName),
      'identify' || 'confirm_person' => l10n.speakerTagPromptWhoIsThis,
      _ => l10n.speakerTagPromptIsThisYou,
    };
    final confirmsGuess = prompt.kind == 'confirm_person' && prompt.suggestedPersonId != null;
    final owner = prompt.kind == 'owner_check';
    NativeRow answer(String id, String title, SpeakerTagAnswer? given, {String? symbol, VoidCallback? custom}) =>
        NativeRow('speaker_review_answer:$id', title,
            symbol: symbol, enabled: enabled, action: (_) => custom != null ? custom() : give(given!));
    final hint = switch (prompt.kind) {
      'confirm_person' when suggestedName != null => null,
      'owner_check' => l10n.speakerTagPromptHintOwner,
      _ => l10n.speakerTagPromptHintIdentify,
    };
    final matched = candidates.any((c) => c.matchLevel != null);
    return [
      NativeSection('speaker_review_clip', [
        NativeRow('speaker_review_play', l10n.speakerTagPromptPlayClip,
            symbol: playing ? 'stop.fill' : 'play.fill', action: (_) => provider.togglePlay(prompt)),
        // Bars come from the clip's own samples once it has been played; nothing is drawn before.
        if (levels.isNotEmpty)
          NativeRow('speaker_review_wave', l10n.speakerTagPromptPlayClip, kind: 'waveform', points: [
            for (final (i, level) in levels.indexed)
              {'x': i.toDouble(), 'y': level.isFinite ? level.clamp(0.0, 1.0) : 0.0, 'label': ''}
          ]),
        NativeRow('speaker_review_duration', OmiDuration.offset(seconds), kind: 'label', symbol: 'clock'),
        if (prompt.excerpt.isNotEmpty)
          NativeRow('speaker_review_excerpt', '“${_nativeText(prompt.excerpt)}”', kind: 'label'),
        if (meta.isNotEmpty) NativeRow('speaker_review_meta', _nativeText(meta), kind: 'label'),
        if (provider.clipErrorPromptId == prompt.id)
          NativeRow('speaker_review_clip_unavailable', l10n.speakerTagPromptClipUnavailable,
              kind: 'label', symbol: 'exclamationmark.circle'),
      ]),
      NativeSection('speaker_review_ask', [
        // PersonAvatar draws initials only, so the suggested person shows as a system symbol.
        NativeRow('speaker_review_question', question,
            kind: 'label', symbol: prompt.kind == 'confirm_person' && suggested != null ? 'person.crop.circle' : null),
      ]),
      if (prompt.kind == 'identify' && candidates.isNotEmpty)
        NativeSection(
            'speaker_review_candidates',
            [
              for (final (index, c) in candidates.indexed)
                NativeRow('speaker_review_candidate:$index', c.name,
                    subtitle: _nativeMatchDescription(context, c),
                    level: _nativeLevel(c.matchLevel),
                    symbol: c.pinned ? 'pin' : null,
                    enabled: enabled,
                    action: (_) => candidate(index)),
            ],
            title: matched ? l10n.speakerTagPromptClosestVoices : l10n.speakerTagPromptRecentPeople),
      NativeSection(
          'speaker_review_answers',
          [
            if (confirmsGuess)
              answer('yes', l10n.yes, null,
                  symbol: 'checkmark',
                  custom: () =>
                      give(SpeakerTagAnswer.person, personId: prompt.suggestedPersonId, displayName: suggestedName)),
            if (owner) answer('me', l10n.speakerTagPromptThatsMeAction, SpeakerTagAnswer.me, symbol: 'checkmark'),
            if (owner)
              answer('not_me', l10n.speakerTagPromptNotMeAction, SpeakerTagAnswer.notMe)
            else
              answer('someone', confirmsGuess ? l10n.speakerTagPromptNoAction : l10n.speakerTagPromptSomeoneElse, null,
                  symbol: confirmsGuess ? null : 'magnifyingglass', custom: () {
                if (!mounted || provider.pending != null || provider.current?.id != prompt.id) return;
                unawaited(answerSpeakerTagWithPicker(context, prompt, candidates, people, give));
              }),
            if (owner)
              answer('not_a_person', l10n.speakerTagPromptNotAPerson, SpeakerTagAnswer.notAPerson, symbol: 'tv'),
            answer('skip', l10n.speakerTagPromptNotSureAction, SpeakerTagAnswer.skip),
            if (provider.answerFailed)
              NativeRow('speaker_review_answer_failed', l10n.speakerTagPromptAnswerFailed,
                  kind: 'label', symbol: 'exclamationmark.circle'),
          ],
          footer: hint ?? ''),
    ];
  }
}

/// "Who Is It?" as a native sheet: search over local query state; That's Me and Not a Person when
/// [offerMeAndNotAPerson]; Add "<query>" or New Person…; I Don't Know when [allowUnknown]; the
/// closest voices, then everyone A to Z. Pops the same [SpeakerPickerChoice] as the Flutter picker,
/// which [fallback] holds.
class NativeSpeakerPicker extends StatefulWidget {
  const NativeSpeakerPicker({
    super.key,
    required this.candidates,
    required this.people,
    required this.fallback,
    this.excludePersonId,
    this.allowUnknown = true,
    this.offerMeAndNotAPerson = false,
  });

  final List<GeneratedSpeakerTagCandidate> candidates;
  final List<Person> people;
  final String? excludePersonId;
  final bool allowUnknown;
  final bool offerMeAndNotAPerson;
  final Widget fallback;

  @override
  State<NativeSpeakerPicker> createState() => _NativeSpeakerPickerState();
}

class _NativeSpeakerPickerState extends State<NativeSpeakerPicker> {
  String _query = '';
  bool _picked = false;

  void _pick(SpeakerPickerChoice choice) {
    if (_picked || !mounted) return;
    _picked = true;
    Navigator.of(context).pop(choice);
  }

  Future<void> _newPerson() async {
    final name = await showSpeakerTagNameDialog(context);
    if (name != null && mounted) _pick(SpeakerPickerChoice.newPerson(name));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final candidates = speakerPickerCandidates(widget.candidates, widget.excludePersonId);
    final people = speakerPickerPeople(widget.people, widget.excludePersonId);
    final q = _query.trim();
    final lower = q.toLowerCase();
    bool matches(String name) => lower.isEmpty || name.toLowerCase().contains(lower);
    // Rows are keyed by person id, so a tap that lands after the filter changed still names that person.
    final seen = <String>{};
    final closest = candidates.where((c) => matches(c.name) && c.personId.isNotEmpty && seen.add(c.personId)).toList();
    final closestIds = {for (final c in closest) c.personId};
    final everyone = people
        .where((p) => matches(p.name) && !closestIds.contains(p.id) && p.id.isNotEmpty && seen.add(p.id))
        .toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
    final exact = people.any((p) => p.name.toLowerCase() == lower);
    final canAdd = q.length >= 2 && q.length <= 40 && !exact;
    return IosNativeSurface(
      title: l10n.whoIsItTitle,
      search: (value) => setState(() => _query = value as String),
      searchValue: _query,
      searchPlaceholder: l10n.peopleSearchPlaceholder,
      toolbar: [
        NativeRow('speaker_picker_close', l10n.close, symbol: 'xmark', action: (_) {
          if (!_picked) Navigator.of(context).maybePop();
        }),
      ],
      sections: [
        if (widget.offerMeAndNotAPerson && q.isEmpty)
          NativeSection('speaker_picker_quick', [
            NativeRow('speaker_picker_me', l10n.speakerTagPromptThatsMeAction,
                symbol: 'person', action: (_) => _pick(const SpeakerPickerChoice.me())),
            NativeRow('speaker_picker_not_a_person', l10n.speakerTagPromptNotAPerson,
                symbol: 'tv', action: (_) => _pick(const SpeakerPickerChoice.notAPerson())),
          ]),
        NativeSection('speaker_picker_add', [
          NativeRow('speaker_picker_new_person', canAdd ? l10n.addNamedPersonAction(q) : l10n.newPersonEllipsis,
              symbol: 'person.badge.plus',
              action: (_) => canAdd ? _pick(SpeakerPickerChoice.newPerson(q)) : _newPerson()),
          if (widget.allowUnknown)
            NativeRow('speaker_picker_unknown', l10n.speakerTagPromptDontKnow,
                symbol: 'questionmark.circle', action: (_) => _pick(const SpeakerPickerChoice.unknown())),
        ]),
        if (closest.isNotEmpty)
          NativeSection(
              'speaker_picker_closest',
              [
                for (final c in closest)
                  NativeRow('speaker_picker_closest:${c.personId}', c.name,
                      subtitle: _nativeMatchDescription(context, c),
                      level: _nativeLevel(c.matchLevel),
                      symbol: c.pinned ? 'pin' : 'person',
                      action: (_) => _pick(SpeakerPickerChoice.person(c.personId, c.name))),
              ],
              title: l10n.speakerTagPromptClosestVoices),
        if (everyone.isNotEmpty)
          NativeSection(
              'speaker_picker_everyone',
              [
                for (final p in everyone)
                  NativeRow('speaker_picker_person:${p.id}', p.name,
                      symbol: 'person.crop.circle', action: (_) => _pick(SpeakerPickerChoice.person(p.id, p.name))),
              ],
              title: l10n.everyoneHeader),
      ],
      fallback: widget.fallback,
    );
  }
}
