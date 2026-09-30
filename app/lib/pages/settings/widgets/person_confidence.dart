import 'package:flutter/material.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Filled steps of the three-step meter for a server confidence band.
int confidenceLevel(String band) => switch (band) {
      'confirmed' => 3,
      'likely' => 2,
      _ => 1,
    };

String confidenceLabel(BuildContext context, String band) => switch (band) {
      'confirmed' => context.l10n.confidenceConfirmed,
      'likely' => context.l10n.confidenceLikely,
      _ => context.l10n.confidenceUnverified,
    };

/// Voice-match levels on suggestions: 3 close, 2 possible, 1 weak.
String voiceMatchLabel(BuildContext context, int level) => switch (level) {
      3 => context.l10n.voiceMatchClose,
      2 => context.l10n.voiceMatchPossible,
      _ => context.l10n.voiceMatchWeak,
    };

class PersonConfidenceMeter extends StatelessWidget {
  const PersonConfidenceMeter({super.key, required this.person, this.size = OmiLevelMeterSize.small});

  final Person person;
  final OmiLevelMeterSize size;

  @override
  Widget build(BuildContext context) => OmiLevelMeter(
        level: confidenceLevel(person.confidence),
        size: size,
        semanticsLabel: context.l10n.confidenceMeterLabel(confidenceLabel(context, person.confidence)),
      );
}

class VoiceMatchMeter extends StatelessWidget {
  const VoiceMatchMeter({super.key, required this.level});

  final int level;

  @override
  Widget build(BuildContext context) =>
      OmiLevelMeter(level: level, semanticsLabel: context.l10n.voiceMatchMeterLabel(voiceMatchLabel(context, level)));
}

/// One line under a person's name: why Omi believes it knows this voice, then what it knows of it.
String personReasonLine(BuildContext context, Person person) {
  final l10n = context.l10n;
  final labeled = person.reasonCount('manual_labels');
  final picked = person.reasonCount('card_picks') + person.reasonCount('card_confirms');
  final confirmed = person.reasonCount('auto_confirmed');
  final String why;
  if (labeled > 0) {
    why = l10n.confidenceReasonLabeled(labeled);
  } else if (picked > 0) {
    why = l10n.confidenceReasonPicked(picked);
  } else if (confirmed > 0) {
    why = l10n.confidenceReasonAutoConfirmed(confirmed);
  } else if (person.reasonCount('auto_corrected') > 0) {
    why = l10n.confidenceReasonCorrected;
  } else if (person.reasonCount('auto_unconfirmed') > 0) {
    why = l10n.confidenceReasonAutoOnly;
  } else {
    why = l10n.confidenceReasonNeverConfirmed;
  }
  final String knows;
  if (person.conversationCount == 0) {
    knows = l10n.confidenceReasonNotHeard;
  } else if (person.voiceReadiness == 'ready') {
    knows = l10n.confidenceReasonVoiceReady;
  } else {
    knows = l10n.confidenceReasonNeedsVoice;
  }
  return '$why · $knows';
}

enum _Effect { alot, counts, little, barely, against, needed, none }

/// "Why Likely?": the evidence behind a person's confidence, what each piece is worth in plain words,
/// and the cheapest way up.
Future<void> showPersonConfidenceSheet(BuildContext context, Person person) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.confidenceSheetTitle,
    builder: (_) => _ConfidenceSheet(person: person),
  );
}

class _ConfidenceSheet extends StatelessWidget {
  const _ConfidenceSheet({required this.person});

  final Person person;

  List<(IconData, String, _Effect)> _evidence(BuildContext context) {
    final l10n = context.l10n;
    final rows = <(IconData, String, _Effect)>[];
    void add(String code, IconData icon, String Function(int) text, _Effect effect) {
      final count = person.reasonCount(code);
      if (count > 0) rows.add((icon, text(count), effect));
    }

    add('manual_labels', Icons.label_outline, l10n.evidenceManualLabels, _Effect.alot);
    add('card_confirms', Icons.check_circle_outline, l10n.evidenceCardConfirms, _Effect.counts);
    add('card_picks', Icons.touch_app_outlined, l10n.evidenceCardPicks, _Effect.counts);
    add('auto_confirmed', Icons.done_all, l10n.evidenceAutoConfirmed, _Effect.little);
    rows.add(person.voiceReadiness == 'ready'
        ? (Icons.graphic_eq, l10n.evidenceVoiceReady, _Effect.counts)
        : (Icons.graphic_eq, l10n.evidenceNoVoice, _Effect.needed));
    add('auto_unconfirmed', Icons.auto_awesome_outlined, l10n.evidenceAutoUnconfirmed, _Effect.barely);
    add('auto_corrected', Icons.swap_horiz, l10n.evidenceAutoCorrected, _Effect.against);
    if (person.conversationCount == 0) rows.add((Icons.hearing_outlined, l10n.evidenceNotHeard, _Effect.none));
    if (person.reasonCount('never_confirmed') > 0) {
      rows.add((Icons.help_outline, l10n.evidenceNothing, _Effect.none));
    }
    return rows;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final name = person.name;
    final summary = switch (person.confidence) {
      'confirmed' => l10n.confidenceSummaryConfirmed(name),
      'likely' => l10n.confidenceSummaryLikely(name),
      _ => l10n.confidenceSummaryUnverified(name),
    };
    final next = <String>[
      if (person.confidence == 'confirmed') l10n.confidenceIsConfirmed(name),
      if (person.confidence != 'confirmed' && (person.labelsToConfirm ?? 0) > 0)
        l10n.confidenceNextLabels(person.labelsToConfirm!),
      if (person.confidence != 'confirmed' && person.voiceReadiness != 'ready') l10n.confidenceNextVoice(name),
    ];
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: OmiSpacing.xs),
          Center(child: PersonConfidenceMeter(person: person, size: OmiLevelMeterSize.large)),
          const SizedBox(height: OmiSpacing.sm),
          Text(confidenceLabel(context, person.confidence), style: OmiType.title3, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xxs),
          Text(
            summary,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiSettingsGroup(
            header: l10n.confidenceEvidenceHeader,
            children: [
              for (final (icon, text, effect) in _evidence(context))
                OmiSettingsRow(
                  leading: Icon(icon),
                  title: text,
                  trailing: effect == _Effect.none ? null : _EffectLabel(effect: effect),
                ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiSettingsGroup(
            header: l10n.confidenceToReachConfirmed,
            footer: l10n.confidenceFootnote,
            children: [for (final line in next) OmiSettingsRow(title: line)],
          ),
        ],
      ),
    );
  }
}

class _EffectLabel extends StatelessWidget {
  const _EffectLabel({required this.effect});

  final _Effect effect;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final (IconData? icon, String text) = switch (effect) {
      _Effect.alot => (Icons.arrow_upward, l10n.effectCountsALot),
      _Effect.counts => (Icons.arrow_upward, l10n.effectCounts),
      _Effect.little => (Icons.arrow_upward, l10n.effectCountsALittle),
      _Effect.barely => (Icons.remove, l10n.effectBarelyCounts),
      _Effect.against => (Icons.arrow_downward, l10n.effectCountsAgainst),
      _Effect.needed => (null, l10n.effectNeeded),
      _Effect.none => (null, ''),
    };
    final raises = icon == Icons.arrow_upward;
    final color = raises ? OmiColors.textPrimary : OmiColors.textSecondary;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) Icon(icon, size: 13, color: color),
        if (icon != null) const SizedBox(width: 2),
        Text(text, style: OmiType.footnote.copyWith(color: color)),
      ],
    );
  }
}
