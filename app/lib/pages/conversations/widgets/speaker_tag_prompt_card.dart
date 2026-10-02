import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Help Omi recognize voices": a small daily set of short clips from the last 48 hours. Each clip
/// plays with its words and when it was said; candidates are ranked by voice match; every answer
/// can be undone for a few seconds before it is sent.
class SpeakerTagPromptCard extends StatefulWidget {
  const SpeakerTagPromptCard({super.key});

  @override
  State<SpeakerTagPromptCard> createState() => _SpeakerTagPromptCardState();
}

class _SpeakerTagPromptCardState extends State<SpeakerTagPromptCard> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<SpeakerTagPromptsProvider>().loadIfDue();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SpeakerTagPromptsProvider>(
      builder: (context, provider, _) {
        if (!provider.visible || (!provider.finished && provider.current == null)) {
          return const SizedBox.shrink();
        }
        return VisibilityDetector(
          key: const Key('speaker_tag_prompt_card_visibility'),
          onVisibilityChanged: (info) {
            if (info.visibleFraction > 0.5) provider.reportShown();
          },
          child: Container(
            key: const Key('speaker_tag_prompt_card'),
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: const BorderRadius.all(Radius.circular(OmiRadius.xl)),
            ),
            margin: const EdgeInsets.fromLTRB(OmiSpacing.md, 15, OmiSpacing.md, 0),
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.md),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Header(provider: provider),
                Padding(
                  padding: const EdgeInsets.only(right: OmiSpacing.xs),
                  child: AnimatedSwitcher(
                    duration: OmiMotion.of(context).standard,
                    child: provider.finished
                        ? _Finished(provider: provider)
                        : provider.pending != null
                            ? _Answered(
                                key: ValueKey('answered_${provider.pending!.promptId}'), pending: provider.pending!)
                            : _Question(key: ValueKey('question_${provider.current!.id}'), provider: provider),
                  ),
                ),
                if (provider.firstTime) ...[
                  const SizedBox(height: OmiSpacing.sm),
                  Divider(color: OmiColors.border, height: 1),
                  const SizedBox(height: OmiSpacing.xs),
                  _SaveVoicesToggle(provider: provider),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.provider});

  final SpeakerTagPromptsProvider provider;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Row(
      children: [
        Icon(Icons.record_voice_over_outlined, color: OmiColors.textPrimary, size: 20),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(
          child: Text(l10n.speakerTagPromptTitle, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
        ),
        if (provider.prompts.length > 1 && !provider.finished)
          Text(
            l10n.speakerTagPromptProgress(
                math.min(provider.index + 1, provider.prompts.length), provider.prompts.length),
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
        OmiIconButton(
          key: const Key('speaker_tag_prompt_close'),
          icon: const Icon(Icons.close, size: 18),
          label: l10n.close,
          color: OmiColors.textSecondary,
          onPressed: provider.close,
        ),
      ],
    );
  }
}

class _Finished extends StatelessWidget {
  const _Finished({required this.provider});

  final SpeakerTagPromptsProvider provider;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text(context.l10n.speakerTagPromptThanks, style: OmiType.subhead)),
        OmiButton.tertiary(
          key: const Key('speaker_tag_prompt_done'),
          label: context.l10n.done,
          size: OmiButtonSize.compact,
          onPressed: provider.close,
        ),
      ],
    );
  }
}

/// Stages an answer, offers Undo for 5 s, then sends it (or drops it on Undo).
Future<void> _giveAnswer(
  BuildContext context,
  SpeakerTagPromptsProvider provider,
  SpeakerTagAnswer answer, {
  String? personId,
  String? name,
  String? displayName,
}) async {
  final l10n = context.l10n;
  if (answer == SpeakerTagAnswer.skip) {
    OmiHaptics.selection();
    await provider.answer(answer);
    return;
  }
  // The question view is replaced by the answered view once staged; toasts need the card's context.
  final host = context.findAncestorStateOfType<_SpeakerTagPromptCardState>()?.context ?? context;
  final people = host.read<PeopleProvider?>();
  OmiHaptics.light();
  provider.stage(answer, personId: personId, name: name, displayName: displayName);
  final message = switch (answer) {
    SpeakerTagAnswer.me => l10n.speakerTagPromptLabeledYouToast,
    SpeakerTagAnswer.notAPerson => l10n.speakerTagPromptNotAPersonToast,
    SpeakerTagAnswer.person ||
    SpeakerTagAnswer.newPerson ||
    SpeakerTagAnswer.someoneElse when displayName != null =>
      l10n.speakerTagPromptLabeledToast(displayName),
    _ => l10n.speakerTagPromptRejectedToast,
  };
  final undone = await OmiFeedback.undo(
    host,
    message,
    onUndo: provider.undoPending,
    icon: answer == SpeakerTagAnswer.notAPerson ? Icons.tv_outlined : Icons.person_outline,
  );
  if (undone) return;
  final saved = await provider.commitPending(
    onSaved: (id) async {
      if (id != null) OmiHaptics.success();
      if (id != null && people != null) await people.refresh();
    },
  );
  if (!saved && host.mounted && provider.answerFailed) {
    OmiFeedback.error(host, l10n.speakerTagPromptAnswerFailed);
  }
}

class _Question extends StatelessWidget {
  const _Question({super.key, required this.provider});

  final SpeakerTagPromptsProvider provider;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final prompt = provider.current!;
    final people = context.watch<PeopleProvider?>()?.people ?? const <Person>[];
    final candidates = _candidates(prompt, people);
    final enabled = !provider.submitting;
    final suggested = people.firstWhereOrNull((p) => p.id == prompt.suggestedPersonId);
    final suggestedName = prompt.suggestedPersonName ?? suggested?.name;
    void give(SpeakerTagAnswer answer, {String? personId, String? name, String? displayName}) {
      if (!enabled) return;
      _giveAnswer(context, provider, answer, personId: personId, name: name, displayName: displayName);
    }

    Future<void> someoneElse() async {
      final choice = await showSpeakerPicker(
        context,
        prompt: prompt,
        candidates: candidates,
        people: people,
        excludePersonId: prompt.suggestedPersonId,
        allowUnknown: prompt.kind != 'owner_check',
      );
      if (choice == null || !context.mounted) return;
      if (choice.unknown) return give(SpeakerTagAnswer.someoneElse);
      if (choice.personId != null) {
        return give(SpeakerTagAnswer.person, personId: choice.personId, displayName: choice.displayName);
      }
      give(SpeakerTagAnswer.newPerson, name: choice.name, displayName: choice.name);
    }

    final question = switch (prompt.kind) {
      'confirm_person' when suggestedName != null && suggestedName.isNotEmpty =>
        l10n.speakerTagPromptIsThisPerson(suggestedName),
      'identify' || 'confirm_person' => l10n.speakerTagPromptWhoIsThis,
      _ => l10n.speakerTagPromptIsThisYou,
    };
    final answers = <Widget>[
      if (prompt.kind == 'confirm_person' && prompt.suggestedPersonId != null)
        _AnswerChip(
          key: const Key('speaker_tag_prompt_answer_yes'),
          label: l10n.yes,
          icon: Icons.check,
          primary: true,
          onPressed: enabled
              ? () => give(SpeakerTagAnswer.person, personId: prompt.suggestedPersonId, displayName: suggestedName)
              : null,
        ),
      if (prompt.kind == 'owner_check')
        _AnswerChip(
          key: const Key('speaker_tag_prompt_answer_me'),
          label: l10n.speakerTagPromptThatsMeAction,
          icon: Icons.check,
          primary: true,
          onPressed: enabled ? () => give(SpeakerTagAnswer.me) : null,
        ),
      if (prompt.kind == 'owner_check')
        _AnswerChip(
          key: const Key('speaker_tag_prompt_answer_not_me'),
          label: l10n.speakerTagPromptNotMeAction,
          onPressed: enabled ? () => give(SpeakerTagAnswer.notMe) : null,
        )
      else
        _AnswerChip(
          key: const Key('speaker_tag_prompt_answer_someone_else'),
          label: l10n.speakerTagPromptSomeoneElse,
          icon: Icons.search,
          onPressed: enabled ? someoneElse : null,
        ),
      if (prompt.kind != 'owner_check')
        _AnswerChip(
          key: const Key('speaker_tag_prompt_answer_me'),
          label: l10n.speakerTagPromptThatsMeAction,
          icon: Icons.person_outline,
          onPressed: enabled ? () => give(SpeakerTagAnswer.me) : null,
        ),
      _AnswerChip(
        key: const Key('speaker_tag_prompt_answer_not_a_person'),
        label: l10n.speakerTagPromptNotAPerson,
        icon: Icons.tv_outlined,
        onPressed: enabled ? () => give(SpeakerTagAnswer.notAPerson) : null,
      ),
      _AnswerChip(
        key: const Key('speaker_tag_prompt_answer_skip'),
        label: l10n.speakerTagPromptNotSureAction,
        onPressed: enabled ? () => give(SpeakerTagAnswer.skip) : null,
      ),
    ];
    final matched = candidates.any((c) => c.matchLevel != null);
    final hint = switch (prompt.kind) {
      'confirm_person' when suggestedName != null => l10n.speakerTagPromptHintConfirm(suggestedName),
      'owner_check' => l10n.speakerTagPromptHintOwner,
      _ => l10n.speakerTagPromptHintIdentify,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: OmiSpacing.xs),
        _Clip(provider: provider, prompt: prompt),
        if (provider.clipErrorPromptId == prompt.id) ...[
          const SizedBox(height: 6),
          Text(l10n.speakerTagPromptClipUnavailable, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
        ],
        const SizedBox(height: OmiSpacing.md),
        Row(
          children: [
            if (prompt.kind == 'confirm_person' && suggested != null) ...[
              PersonAvatar(person: suggested, size: 36, showVoiceBadge: false),
              const SizedBox(width: OmiSpacing.sm),
            ],
            Expanded(child: Text(question, style: OmiType.headline)),
          ],
        ),
        if (prompt.kind == 'identify' && candidates.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(
            matched ? l10n.speakerTagPromptClosestVoices : l10n.speakerTagPromptRecentPeople,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.xxs),
          Wrap(
            spacing: OmiSpacing.xs,
            runSpacing: OmiSpacing.xs,
            children: [
              for (final candidate in candidates)
                _CandidateChip(
                  candidate: candidate,
                  onPressed: enabled
                      ? () => give(SpeakerTagAnswer.person, personId: candidate.personId, displayName: candidate.name)
                      : null,
                ),
            ],
          ),
        ],
        const SizedBox(height: OmiSpacing.xs),
        Wrap(spacing: OmiSpacing.xs, children: answers),
        if (provider.answerFailed) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(l10n.speakerTagPromptAnswerFailed, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
        ],
        const SizedBox(height: OmiSpacing.sm),
        Divider(color: OmiColors.border, height: 1),
        const SizedBox(height: OmiSpacing.sm),
        Row(
          children: [
            Icon(Icons.arrow_upward, size: 14, color: OmiColors.textSecondary),
            const SizedBox(width: OmiSpacing.xxs),
            Expanded(child: Text(hint, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
          ],
        ),
      ],
    );
  }
}

/// Server-ranked candidates when present (voice match, pinned first within a level); otherwise the
/// legacy recency list, looked up in the people list.
List<GeneratedSpeakerTagCandidate> _candidates(GeneratedSpeakerTagPrompt prompt, List<Person> people) {
  final ranked = prompt.candidates ?? const <GeneratedSpeakerTagCandidate>[];
  if (ranked.isNotEmpty) return ranked;
  final byId = {for (final person in people) person.id: person};
  return [
    for (final id in prompt.suggestedPersonIds ?? const <String>[])
      if (byId[id] != null) GeneratedSpeakerTagCandidate(personId: id, name: byId[id]!.name, pinned: byId[id]!.pinned),
  ];
}

class _Clip extends StatelessWidget {
  const _Clip({required this.provider, required this.prompt});

  final SpeakerTagPromptsProvider provider;
  final GeneratedSpeakerTagPrompt prompt;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final playing = provider.playingPromptId == prompt.id;
    final started = prompt.conversationStartedAt?.toLocal();
    final seconds = math.max(0, (prompt.clipEnd - prompt.clipStart).round());
    final wav = provider.clipFor(prompt.id);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, OmiSpacing.xs, OmiSpacing.sm, OmiSpacing.xs),
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
          child: Row(
            children: [
              Semantics(
                button: true,
                label: l10n.speakerTagPromptPlayClip,
                excludeSemantics: true,
                onTap: () => provider.togglePlay(prompt),
                child: InkWell(
                  key: const Key('speaker_tag_prompt_play'),
                  customBorder: const CircleBorder(),
                  onTap: () => provider.togglePlay(prompt),
                  child: Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                    child: Icon(
                      playing ? Icons.stop_rounded : Icons.play_arrow_rounded,
                      color: OmiColors.onAccent,
                      size: 26,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(child: SizedBox(height: 28, child: _Waveform(wav: wav))),
              const SizedBox(width: OmiSpacing.sm),
              Text(OmiDuration.offset(seconds), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
        if (prompt.excerpt.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.xs),
          Text(
            '“${prompt.excerpt}”',
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: OmiType.subhead,
          ),
        ],
        if (prompt.conversationTitle.isNotEmpty || started != null) ...[
          const SizedBox(height: OmiSpacing.xxs),
          Text.rich(
            TextSpan(
              children: [
                if (prompt.conversationTitle.isNotEmpty)
                  TextSpan(
                    text: prompt.conversationTitle,
                    style: TextStyle(color: OmiColors.textPrimary, fontWeight: FontWeight.w500),
                  ),
                if (prompt.conversationTitle.isNotEmpty && started != null) const TextSpan(text: ' · '),
                if (started != null) TextSpan(text: OmiDateFormat.of(context).timestamp(started)),
              ],
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
        ],
      ],
    );
  }
}

/// Bars drawn from the clip's own samples once it has been played; a flat track before that, so the
/// card never draws a waveform that is not the voice.
class _Waveform extends StatelessWidget {
  const _Waveform({required this.wav});

  final Uint8List? wav;

  @override
  Widget build(BuildContext context) {
    final levels = wav == null ? null : waveformLevels(wav!, bars: 40);
    return ExcludeSemantics(
      child: CustomPaint(
        painter: _WaveformPainter(
          levels: levels,
          color: OmiColors.textPrimary,
          track: OmiColors.textPrimary.withValues(alpha: 0.18),
        ),
      ),
    );
  }
}

/// RMS of 16-bit mono PCM after a 44-byte WAV header, in [bars] buckets scaled to 0..1.
@visibleForTesting
List<double> waveformLevels(Uint8List wav, {int bars = 40}) {
  const header = 44;
  if (wav.length <= header + 2 || bars <= 0) return const [];
  final samples = ByteData.sublistView(wav, header);
  final count = samples.lengthInBytes ~/ 2;
  final perBar = math.max(1, count ~/ bars);
  final levels = <double>[];
  for (var bar = 0; bar < bars && bar * perBar < count; bar++) {
    var sum = 0.0;
    final end = math.min(count, (bar + 1) * perBar);
    for (var i = bar * perBar; i < end; i++) {
      final v = samples.getInt16(i * 2, Endian.little) / 32768.0;
      sum += v * v;
    }
    levels.add(math.sqrt(sum / (end - bar * perBar)));
  }
  final peak = levels.fold<double>(0, math.max);
  return peak <= 0 ? levels.map((_) => 0.0).toList() : levels.map((v) => v / peak).toList();
}

class _WaveformPainter extends CustomPainter {
  _WaveformPainter({required this.levels, required this.color, required this.track});

  final List<double>? levels;
  final Color color;
  final Color track;

  @override
  void paint(Canvas canvas, Size size) {
    final values = levels;
    if (values == null || values.isEmpty) {
      final paint = Paint()
        ..color = track
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round;
      canvas.drawLine(Offset(0, size.height / 2), Offset(size.width, size.height / 2), paint);
      return;
    }
    final step = size.width / values.length;
    final paint = Paint()
      ..color = color
      ..strokeWidth = math.max(1.5, step * 0.55)
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < values.length; i++) {
      final h = math.max(2.0, values[i] * size.height);
      final x = step * (i + 0.5);
      canvas.drawLine(Offset(x, (size.height - h) / 2), Offset(x, (size.height + h) / 2), paint);
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter old) => old.levels != levels || old.color != color;
}

class _CandidateChip extends StatelessWidget {
  const _CandidateChip({required this.candidate, required this.onPressed});

  final GeneratedSpeakerTagCandidate candidate;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final level = candidate.matchLevel;
    return Semantics(
      button: true,
      enabled: onPressed != null,
      onTap: onPressed,
      label: [
        candidate.name,
        if (candidate.pinned) context.l10n.peopleFilterPinned,
        if (level != null) context.l10n.voiceMatchMeterLabel(voiceMatchLabel(context, level)),
      ].join(', '),
      excludeSemantics: true,
      child: InkWell(
        key: Key('speaker_tag_prompt_candidate_${candidate.personId}'),
        borderRadius: OmiRadius.pillAll,
        onTap: onPressed,
        child: Container(
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          decoration: BoxDecoration(
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: OmiColors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(child: Text(candidate.name, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500))),
              if (candidate.pinned) ...[
                const SizedBox(width: OmiSpacing.xxs),
                Icon(Icons.push_pin, size: 12, color: OmiColors.textTertiary),
              ],
              if (level != null) ...[
                const SizedBox(width: OmiSpacing.xs),
                VoiceMatchMeter(level: level),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _AnswerChip extends StatelessWidget {
  const _AnswerChip({super.key, required this.label, required this.onPressed, this.primary = false, this.icon});

  final String label;
  final VoidCallback? onPressed;
  final bool primary;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final foreground = primary ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      enabled: onPressed != null,
      label: label,
      excludeSemantics: true,
      onTap: onPressed,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onPressed,
        // 36pt chip inside a 44pt target (contract §3).
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: AnimatedOpacity(
            duration: OmiMotion.of(context).quick,
            opacity: onPressed == null ? 0.4 : 1,
            child: Container(
              constraints: const BoxConstraints(minHeight: 36),
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(
                color: primary ? OmiColors.accent : OmiColors.chipSurface,
                borderRadius: OmiRadius.pillAll,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[Icon(icon, size: 16, color: foreground), const SizedBox(width: 6)],
                  Flexible(
                    child: Text(
                      label,
                      style: OmiType.subhead
                          .copyWith(color: foreground, fontWeight: primary ? FontWeight.w600 : FontWeight.w500),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The answer on screen during its Undo window and just after it commits: who the voice was saved as,
/// and that person's meter, which ticks up once the refreshed confidence arrives.
class _Answered extends StatelessWidget {
  const _Answered({super.key, required this.pending});

  /// A snapshot: the view keeps building while it animates out after the provider clears it.
  final PendingSpeakerTagAnswer pending;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final person = context.watch<PeopleProvider?>()?.people.firstWhereOrNull((p) => p.id == pending.personId);
    final (IconData icon, String text) = switch (pending.answer) {
      SpeakerTagAnswer.me => (Icons.person_outline, l10n.speakerTagPromptSavedAsYou),
      SpeakerTagAnswer.notAPerson => (Icons.tv_outlined, l10n.speakerTagPromptIgnoredNote),
      _ when pending.displayName != null => (Icons.person_outline, l10n.speakerTagPromptSavedAs(pending.displayName!)),
      _ => (Icons.person_off_outlined, l10n.speakerTagPromptRejectedToast),
    };
    return Container(
      key: const Key('speaker_tag_prompt_answered'),
      margin: const EdgeInsets.only(top: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      child: Row(
        children: [
          if (person != null)
            PersonAvatar(person: person, size: 36, showVoiceBadge: false)
          else
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.surface3, shape: BoxShape.circle),
              child: Icon(icon, size: 18, color: OmiColors.textPrimary),
            ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(text, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500)),
                if (person != null) ...[
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      PersonConfidenceMeter(person: person),
                      const SizedBox(width: 6),
                      Text(
                        confidenceLabel(context, person.confidence),
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          if (pending.committed) Icon(Icons.check_circle, size: 22, color: OmiColors.success),
        ],
      ),
    );
  }
}

/// What the Someone Else… picker returned: an existing person, a new name, or "someone I don't know".
class SpeakerPickerChoice {
  const SpeakerPickerChoice.person(String this.personId, this.displayName)
      : name = null,
        unknown = false;
  const SpeakerPickerChoice.newPerson(String this.name)
      : personId = null,
        displayName = null,
        unknown = false;
  const SpeakerPickerChoice.unknown()
      : personId = null,
        name = null,
        displayName = null,
        unknown = true;

  final String? personId;
  final String? name;
  final String? displayName;
  final bool unknown;
}

/// "Who Is It?": search, a new person, the closest voices (without the person just ruled out), then
/// everyone A to Z.
Future<SpeakerPickerChoice?> showSpeakerPicker(
  BuildContext context, {
  required GeneratedSpeakerTagPrompt prompt,
  required List<GeneratedSpeakerTagCandidate> candidates,
  required List<Person> people,
  String? excludePersonId,
  bool allowUnknown = true,
}) {
  return showOmiSheet<SpeakerPickerChoice>(
    context: context,
    title: context.l10n.whoIsItTitle,
    builder: (sheetContext) => _SpeakerPicker(
      candidates: candidates.where((c) => c.personId != excludePersonId).toList(),
      people: people.where((p) => p.id != excludePersonId && !p.id.startsWith('optimistic-person:')).toList(),
      allowUnknown: allowUnknown,
    ),
  );
}

class _SpeakerPicker extends StatefulWidget {
  const _SpeakerPicker({required this.candidates, required this.people, required this.allowUnknown});

  final List<GeneratedSpeakerTagCandidate> candidates;
  final List<Person> people;
  final bool allowUnknown;

  @override
  State<_SpeakerPicker> createState() => _SpeakerPickerState();
}

class _SpeakerPickerState extends State<_SpeakerPicker> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _pick(SpeakerPickerChoice choice) => Navigator.of(context).pop(choice);

  Future<void> _newPerson() async {
    final name = await showDialog<String>(context: context, builder: (_) => const _NameDialog());
    if (name != null && mounted) _pick(SpeakerPickerChoice.newPerson(name));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final q = _query.trim();
    final lower = q.toLowerCase();
    bool matches(String name) => lower.isEmpty || name.toLowerCase().contains(lower);
    final closest = widget.candidates.where((c) => matches(c.name)).toList();
    final closestIds = {for (final c in closest) c.personId};
    final everyone = widget.people.where((p) => matches(p.name) && !closestIds.contains(p.id)).toList()
      ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
    final exact = widget.people.any((p) => p.name.toLowerCase() == lower);
    final canAdd = q.length >= 2 && q.length <= 40 && !exact;
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
        children: [
          OmiSearchField(
            placeholder: l10n.peopleSearchPlaceholder,
            controller: _search,
            onChanged: (value) => setState(() => _query = value),
            onCleared: () => setState(() => _query = ''),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const Key('speaker_picker_new_person'),
                leading: const Icon(Icons.person_add_alt_outlined),
                title: canAdd ? l10n.addNamedPersonAction(q) : l10n.newPersonEllipsis,
                onTap: canAdd ? () => _pick(SpeakerPickerChoice.newPerson(q)) : _newPerson,
              ),
              if (widget.allowUnknown)
                OmiSettingsRow(
                  key: const Key('speaker_picker_unknown'),
                  leading: const Icon(Icons.help_outline),
                  title: l10n.speakerTagPromptDontKnow,
                  onTap: () => _pick(const SpeakerPickerChoice.unknown()),
                ),
            ],
          ),
          if (closest.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.md),
            OmiSettingsGroup(
              header: l10n.speakerTagPromptClosestVoices,
              children: [
                for (final c in closest)
                  OmiSettingsRow(
                    key: Key('speaker_picker_person_${c.personId}'),
                    title: c.name,
                    leading: c.pinned ? const Icon(Icons.push_pin) : const Icon(Icons.person_outline),
                    trailing: c.matchLevel == null ? null : VoiceMatchMeter(level: c.matchLevel!),
                    onTap: () => _pick(SpeakerPickerChoice.person(c.personId, c.name)),
                  ),
              ],
            ),
          ],
          if (everyone.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.md),
            OmiSettingsGroup(
              header: l10n.everyoneHeader,
              children: [
                for (final p in everyone)
                  OmiSettingsRow(
                    key: Key('speaker_picker_person_${p.id}'),
                    title: p.name,
                    leading: PersonAvatar(person: p, size: 32, showVoiceBadge: false),
                    onTap: () => _pick(SpeakerPickerChoice.person(p.id, p.name)),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _NameDialog extends StatefulWidget {
  const _NameDialog();

  @override
  State<_NameDialog> createState() => _NameDialogState();
}

class _NameDialogState extends State<_NameDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _valid {
    final length = _controller.text.trim().length;
    return length >= 2 && length <= 40;
  }

  @override
  Widget build(BuildContext context) {
    return OmiAlertDialog(
      title: context.l10n.speakerTagPromptWhoIsThis,
      // The Cupertino dialog has no Material ancestor; the text field needs one.
      content: Material(
        type: MaterialType.transparency,
        child: TextField(
          key: const Key('speaker_tag_prompt_name_field'),
          controller: _controller,
          autofocus: true,
          maxLength: 40,
          textCapitalization: TextCapitalization.words,
          decoration: InputDecoration(hintText: context.l10n.speakerTagPromptNameHint),
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) {
            if (_valid) Navigator.of(context).pop(_controller.text.trim());
          },
        ),
      ),
      actions: [
        OmiDialogAction(label: context.l10n.cancel, onPressed: () => Navigator.of(context).pop()),
        OmiDialogAction(
          key: const Key('speaker_tag_prompt_name_save'),
          label: context.l10n.save,
          isDefault: true,
          onPressed: _valid ? () => Navigator.of(context).pop(_controller.text.trim()) : null,
        ),
      ],
    );
  }
}

class _SaveVoicesToggle extends StatelessWidget {
  const _SaveVoicesToggle({required this.provider});

  final SpeakerTagPromptsProvider provider;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.speakerTagPromptSaveVoicesTitle,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 2),
              Text(
                context.l10n.speakerTagPromptSaveVoicesBody,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ],
          ),
        ),
        OmiSwitch(
          key: const Key('speaker_tag_prompt_save_voices_switch'),
          value: provider.saveOtherVoiceProfiles,
          onChanged: (value) => provider.setSaveOtherVoiceProfiles(value, fromFirstPrompt: true),
        ),
      ],
    );
  }
}
