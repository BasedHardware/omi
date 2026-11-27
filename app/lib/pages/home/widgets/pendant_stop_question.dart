// Presents the one-tap pendant-stop survey through the Home prompt queue.
// The typed answer and the optional private note take separate delivery paths.
import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/services/experiments/pendant_absence.dart';
import 'package:omi/services/experiments/pendant_stop_question_policy.dart';
import 'package:omi/ui/components/omi_sheet.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

typedef _Reason = PendantStopQuestionAnsweredReason;
typedef _Answer = ({_Reason reason, String note});

class PendantStopQuestion {
  static const promptId = 'pendant-stop-question';

  static void enqueue({
    required PromptQueue queue,
    required PendantAbsence absence,
    required String uid,
    required bool Function() isCurrentUser,
    required int? Function() eligibleDays,
    required PendantStopQuestionAnsweredPlan Function() plan,
    Future<bool> Function()? disabled,
    void Function(RegisteredEvent)? emit,
    Future<void> Function(String uid, PendantStopQuestionAnsweredReason reason, String note, int days)? sendNote,
  }) {
    final track = emit ?? const TypedEvents().emit;

    int? currentGap() {
      if (!isCurrentUser() || absence.questionShown(uid) || absence.surfaceShownToday) return null;
      return eligibleDays();
    }

    if (currentGap() == null) return;
    queue.enqueue(
      promptId,
      PromptPriority.low,
      canShowNow: () => currentGap() != null,
      show: (context) async {
        if (await (disabled?.call() ?? PendantStopQuestionPolicy.disabled())) return;
        if (!context.mounted || queue.blocked()) return;
        final days = currentGap();
        if (days == null || !absence.claimQuestion(uid)) return;

        final answerFuture = showOmiSheet<_Answer>(
          context: context,
          title: context.l10n.pendantStopQuestionTitle,
          useRootNavigator: true,
          builder: (_) => const _QuestionBody(),
        );
        track(const PendantStopQuestionShown());
        final answer = await answerFuture;
        if (!context.mounted || !isCurrentUser()) return;
        if (answer == null) {
          track(const PendantStopQuestionDismissed());
          return;
        }
        track(PendantStopQuestionAnswered(
          reason: answer.reason,
          daysWithoutConnection: days,
          noteProvided: answer.note.isNotEmpty,
          plan: plan(),
        ));
        OmiFeedback.confirm(context, context.l10n.pendantStopQuestionThanks);
        if (answer.note.isNotEmpty) {
          unawaited(
              Future<void>.sync(() => (sendNote ?? submitPendantStopFeedback)(uid, answer.reason, answer.note, days))
                  .catchError((Object error) {
            Logger.debug('Pendant feedback note delivery failed: ${error.runtimeType}');
          }));
        }
      },
    );
    queue.pump();
  }
}

class _QuestionBody extends StatefulWidget {
  const _QuestionBody();

  @override
  State<_QuestionBody> createState() => _QuestionBodyState();
}

class _QuestionBodyState extends State<_QuestionBody> {
  final _note = TextEditingController();

  void _answer(_Reason reason) {
    if (ModalRoute.of(context)?.isCurrent != true) return;
    Navigator.of(context).pop<_Answer>((reason: reason, note: _note.text.trim()));
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final labels = {
      _Reason.uncomfortableToWear: l10n.pendantStopReasonUncomfortable,
      _Reason.forgotOrNoHabit: l10n.pendantStopReasonHabit,
      _Reason.chargingIsAHassle: l10n.pendantStopReasonCharging,
      _Reason.notUsefulEnough: l10n.pendantStopReasonValue,
      _Reason.deviceProblem: l10n.pendantStopReasonDevice,
      _Reason.other: l10n.pendantStopReasonOther,
    };
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final entry in labels.entries) ListTile(title: Text(entry.value), onTap: () => _answer(entry.key)),
          const SizedBox(height: OmiSpacing.sm),
          TextField(
            key: const Key('pendant-stop-note'),
            controller: _note,
            decoration: InputDecoration(labelText: l10n.pendantStopOptionalNote),
            maxLines: 3,
            minLines: 1,
            maxLength: 500,
          ),
          ValueListenableBuilder(
            valueListenable: _note,
            builder: (context, note, _) => Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TextButton(
                key: const Key('pendant-stop-send-note'),
                onPressed: note.text.trim().isEmpty ? null : () => _answer(_Reason.other),
                child: Text(l10n.pendantStopSendNote),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
