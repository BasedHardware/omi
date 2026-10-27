import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/speaker_picker.dart';

/// The one detail sheet every Review question opens: the question, the evidence (the only part
/// that differs by kind), and every answer. The sheet returns to whatever screen opened it.
Future<void> showReviewItemSheet(BuildContext context, ReviewItem item) {
  final provider = context.read<ReviewProvider>();
  return showOmiSheet<void>(
    context: context,
    title: reviewQuestion(context, item),
    builder: (sheetContext) => ChangeNotifierProvider<ReviewProvider>.value(
      value: provider,
      child: SingleChildScrollView(
        padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.md),
        child: ReviewItemDetail(item: item),
      ),
    ),
  );
}

/// The body of the detail sheet. Public so the visual audit can render it without a route.
class ReviewItemDetail extends StatelessWidget {
  const ReviewItemDetail({super.key, required this.item, this.onDone});

  final ReviewItem item;

  /// Called after an answer is sent; defaults to closing the sheet.
  final VoidCallback? onDone;

  @override
  Widget build(BuildContext context) {
    void done() => onDone != null ? onDone!() : Navigator.of(context).maybePop();
    return switch (item.kind) {
      ReviewItemKind.speaker => _SpeakerDetail(item: item, onDone: done),
      ReviewItemKind.task => _TaskDetail(item: item, onDone: done),
      ReviewItemKind.samePerson => _SamePersonDetail(item: item, onDone: done),
      ReviewItemKind.spelling => _SpellingDetail(item: item, onDone: done),
      ReviewItemKind.agentProposal => _ProposalDetail(item: item, onDone: done),
    };
  }
}

Future<void> _send(BuildContext context, ReviewItem item, ReviewAnswer answer, VoidCallback onDone) async {
  onDone();
  await answerReviewItem(context, item, answer);
}

class _EvidenceBox extends StatelessWidget {
  const _EvidenceBox({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }
}

class _Actions extends StatelessWidget {
  const _Actions({required this.primary, this.secondary = const []});

  final Widget primary;
  final List<Widget> secondary;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.md),
      child: Row(
        children: [
          Expanded(child: primary),
          for (final widget in secondary) ...[const SizedBox(width: OmiSpacing.xs), Expanded(child: widget)],
        ],
      ),
    );
  }
}

// --- Speaker -------------------------------------------------------------------------------

class _SpeakerDetail extends StatefulWidget {
  const _SpeakerDetail({required this.item, required this.onDone});

  final ReviewItem item;
  final VoidCallback onDone;

  @override
  State<_SpeakerDetail> createState() => _SpeakerDetailState();
}

class _SpeakerChoice {
  const _SpeakerChoice.person(this.personId) : isMe = false;
  const _SpeakerChoice.me()
      : personId = null,
        isMe = true;

  final String? personId;
  final bool isMe;

  @override
  bool operator ==(Object other) => other is _SpeakerChoice && other.personId == personId && other.isMe == isMe;

  @override
  int get hashCode => Object.hash(personId, isMe);
}

class _SpeakerDetailState extends State<_SpeakerDetail> {
  _SpeakerChoice? _choice;

  /// A name picked as a brand-new person in the picker, waiting on Confirm.
  String? _newName;

  @override
  void initState() {
    super.initState();
    final first = widget.item.speaker!.candidates.firstOrNull;
    if (first != null) _choice = _SpeakerChoice.person(first.personId);
  }

  /// "Someone Else…": the shared picker searches every person, so an existing speaker can be
  /// picked by id instead of a lookalike new name.
  Future<void> _someoneElse() async {
    final speaker = widget.item.speaker!;
    final people = context.read<PeopleProvider?>()?.people ?? const <Person>[];
    final choice = await showSpeakerPicker(
      context,
      candidates: [
        for (final c in speaker.candidates) SpeakerPickerCandidate(personId: c.personId, name: c.name),
      ],
      people: people,
      // The sheet's own Not Sure button already covers "don't know".
      allowUnknown: false,
    );
    if (choice == null || !mounted) return;
    setState(() {
      if (choice.personId != null) {
        _choice = _SpeakerChoice.person(choice.personId!);
        _newName = null;
      } else if (choice.name != null) {
        _choice = null;
        _newName = choice.name;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<ReviewProvider>();
    final speaker = widget.item.speaker!;
    final people = context.watch<PeopleProvider?>()?.people ?? const <Person>[];
    final playing = provider.playingItemId == widget.item.itemId;
    final chosenName = _newName ??
        switch (_choice) {
          _SpeakerChoice(isMe: true) => l10n.reviewAnswerMe,
          _SpeakerChoice(:final personId?) =>
            speaker.candidates.where((c) => c.personId == personId).map((c) => c.name).firstOrNull ??
                people.where((p) => p.id == personId).map((p) => p.name).firstOrNull,
          _ => null,
        };
    final canConfirm = _newName != null || _choice != null;

    Widget choice({required String label, String? subtitle, required _SpeakerChoice value, required Widget avatar}) {
      final selected = _choice == value;
      return Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Material(
          color: OmiColors.surface2,
          shape: RoundedRectangleBorder(
            borderRadius: const BorderRadius.all(Radius.circular(14)),
            side: BorderSide(color: selected ? OmiColors.accent : Colors.transparent, width: 2),
          ),
          child: InkWell(
            borderRadius: const BorderRadius.all(Radius.circular(14)),
            onTap: () => setState(() {
              _newName = null;
              _choice = value;
            }),
            child: Semantics(
              selected: selected,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 52),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(10, 6, 14, 6),
                  child: Row(
                    children: [
                      avatar,
                      const SizedBox(width: OmiSpacing.sm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(label, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                            if (subtitle != null)
                              Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                          ],
                        ),
                      ),
                      Icon(
                        selected ? Icons.check_circle : Icons.radio_button_unchecked,
                        color: selected ? OmiColors.accent : OmiColors.textTertiary,
                        size: 22,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(10, 10, 14, 10),
          decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
          child: Row(
            children: [
              ReviewPlayButton(playing: playing, onPressed: () => provider.togglePlay(widget.item)),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: _Waveform(seed: speaker.promptId.hashCode, active: playing),
              ),
            ],
          ),
        ),
        if (speaker.affectedConversationCount > 1)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.xxs, 0),
            child: Text(
              l10n.reviewAnswersConversations(speaker.affectedConversationCount),
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        if (speaker.context.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.sm),
          for (final line in speaker.context) _TranscriptLineView(line: line),
        ],
        const SizedBox(height: OmiSpacing.md),
        for (final person in speaker.candidates)
          choice(
            label: person.name,
            subtitle: person.organization,
            value: _SpeakerChoice.person(person.personId),
            avatar: EntityInitialAvatar(name: person.name, type: EntityType.person, size: 32),
          ),
        choice(
          label: l10n.reviewAnswerMe,
          value: const _SpeakerChoice.me(),
          avatar: Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(color: OmiColors.surface3, shape: BoxShape.circle),
            child: Icon(Icons.person, size: 18, color: OmiColors.textPrimary),
          ),
        ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: OmiButton.tertiary(
            key: const Key('review_speaker_someone_else'),
            label: l10n.reviewSomeoneElse,
            icon: Icons.search,
            // Fire-and-forget: the picker is modal, and a pending future would spin this button
            // for as long as the user keeps it open.
            onPressed: () {
              _someoneElse();
            },
          ),
        ),
        _Actions(
          primary: OmiButton(
            key: const Key('review_speaker_confirm'),
            label: chosenName == null ? l10n.reviewConfirm : l10n.reviewConfirmPerson(chosenName),
            onPressed: canConfirm
                ? () => _send(
                      context,
                      widget.item,
                      _newName != null
                          ? ReviewAnswer.speaker(newName: _newName)
                          : _choice!.isMe
                              ? const ReviewAnswer.speaker(isMe: true)
                              : ReviewAnswer.speaker(personId: _choice!.personId),
                      widget.onDone,
                    )
                : null,
          ),
          secondary: [
            OmiButton.secondary(
              label: l10n.reviewNotSure,
              onPressed: () => _send(context, widget.item, const ReviewAnswer.notSure(), widget.onDone),
            ),
          ],
        ),
      ],
    );
  }
}

class _TranscriptLineView extends StatelessWidget {
  const _TranscriptLineView({required this.line});

  final TranscriptLine line;

  @override
  Widget build(BuildContext context) {
    final time = line.at == null ? null : OmiDateFormat.of(context).time(line.at!);
    final label = line.isTarget ? context.l10n.reviewUnknownSpeaker : line.speakerLabel;
    return Container(
      margin: const EdgeInsets.only(bottom: OmiSpacing.xxs),
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
      decoration: line.isTarget
          ? BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll)
          : const BoxDecoration(),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: line.isTarget ? Colors.transparent : OmiColors.surface3,
              border: line.isTarget ? Border.all(color: OmiColors.textTertiary, width: 1.5) : null,
            ),
            child: Text(
              line.isTarget ? '?' : (label.isEmpty ? '?' : label.characters.first.toUpperCase()),
              style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: label,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      if (time != null)
                        TextSpan(
                          text: ' · $time',
                          style: TextStyle(color: OmiColors.textSecondary),
                        ),
                    ],
                  ),
                  style: OmiType.footnote,
                ),
                const SizedBox(height: 2),
                Text(line.text, style: OmiType.subhead),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Decorative bars for a clip. They brighten while it plays; they do not track the audio.
class _Waveform extends StatelessWidget {
  const _Waveform({required this.seed, required this.active});

  final int seed;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final heights = List<double>.generate(28, (i) {
      final v = ((seed >> (i % 16)) ^ (i * 2654435761)) & 0x1f;
      return 8 + v.toDouble();
    });
    return ExcludeSemantics(
      child: SizedBox(
        height: 44,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final count = (constraints.maxWidth / 7).floor().clamp(1, heights.length);
            return Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (var i = 0; i < count; i++)
                  Container(
                    width: 4,
                    height: heights[i],
                    decoration: BoxDecoration(
                      color: active ? OmiColors.textPrimary : OmiColors.textDisabled,
                      borderRadius: const BorderRadius.all(Radius.circular(2)),
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}

// --- Task ----------------------------------------------------------------------------------

class _TaskDetail extends StatefulWidget {
  const _TaskDetail({required this.item, required this.onDone});

  final ReviewItem item;
  final VoidCallback onDone;

  @override
  State<_TaskDetail> createState() => _TaskDetailState();
}

class _TaskDetailState extends State<_TaskDetail> {
  late final TextEditingController _title = TextEditingController(text: widget.item.task!.description);
  late DateTime? _dueAt = widget.item.task!.dueAt;
  bool _choosingReason = false;

  @override
  void dispose() {
    _title.dispose();
    super.dispose();
  }

  Future<void> _pickDue() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _dueAt ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
    );
    if (picked != null && mounted) setState(() => _dueAt = picked);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final task = widget.item.task!;
    final evidence = task.evidence;
    final dates = OmiDateFormat.of(context);
    void dismiss([TaskDismissReason? reason]) =>
        _send(context, widget.item, ReviewAnswer.dismissTask(reason), widget.onDone);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (evidence != null)
          _EvidenceBox(
            children: [
              Text('“${evidence.quote}”', style: OmiType.callout),
              const SizedBox(height: OmiSpacing.xs),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      [
                        if (evidence.speakerLabel != null) evidence.speakerLabel!,
                        if (evidence.at != null) dates.time(evidence.at!),
                      ].join(' · '),
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                    ),
                  ),
                  if (evidence.conversationId != null)
                    Flexible(
                      child: ReviewLinkChip(
                        label: evidence.conversationTitle ?? l10n.reviewOpenConversation,
                        icon: Icons.chat_bubble_outline,
                        onTap: () => openChatBlockConversation(context, conversationId: evidence.conversationId!),
                      ),
                    ),
                ],
              ),
            ],
          ),
        const SizedBox(height: OmiSpacing.md),
        TextField(
          key: const Key('review_task_title'),
          controller: _title,
          maxLines: null,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(labelText: l10n.reviewTaskField),
        ),
        const SizedBox(height: OmiSpacing.sm),
        _FieldRow(
          icon: Icons.event_outlined,
          title: l10n.reviewDue,
          value: _dueAt == null ? l10n.reviewNoDate : dates.date(_dueAt!),
          onTap: _pickDue,
        ),
        if (task.workstreamTitle != null) ...[
          const SizedBox(height: OmiSpacing.xs),
          _FieldRow(icon: Icons.folder_outlined, title: l10n.reviewProject, value: task.workstreamTitle!),
        ],
        _Actions(
          primary: OmiButton(
            key: const Key('review_task_add'),
            label: l10n.reviewAddTask,
            onPressed: () {
              final edited = _title.text.trim();
              _send(
                context,
                widget.item,
                ReviewAnswer.acceptTask(
                  description: edited.isEmpty || edited == task.description ? null : edited,
                  dueAt: _dueAt,
                  workstreamId: task.workstreamId,
                ),
                widget.onDone,
              );
            },
          ),
          secondary: [
            OmiButton.secondary(
              key: const Key('review_task_dismiss'),
              label: l10n.dismiss,
              onPressed: () => setState(() => _choosingReason = true),
            ),
          ],
        ),
        AnimatedSize(
          duration: OmiMotion.of(context).standard,
          child: !_choosingReason
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.sm),
                  child: Wrap(
                    spacing: OmiSpacing.xs,
                    runSpacing: OmiSpacing.xs,
                    children: [
                      ReviewAnswerPill(
                        label: l10n.reviewReasonAlreadyDone,
                        onPressed: () => dismiss(TaskDismissReason.alreadyDone),
                      ),
                      ReviewAnswerPill(
                        label: l10n.reviewReasonNotMine,
                        onPressed: () => dismiss(TaskDismissReason.notMine),
                      ),
                      ReviewAnswerPill(
                        label: l10n.reviewReasonNotUseful,
                        onPressed: () => dismiss(TaskDismissReason.notUseful),
                      ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}

/// A labelled value on the sheet's raised surface; tappable when [onTap] is set.
class _FieldRow extends StatelessWidget {
  const _FieldRow({required this.icon, required this.title, required this.value, this.onTap});

  final IconData icon;
  final String title;
  final String value;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: OmiColors.surface2,
      borderRadius: OmiRadius.mdAll,
      child: InkWell(
        borderRadius: OmiRadius.mdAll,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 8, 0),
            child: Row(
              children: [
                Icon(icon, size: 18, color: OmiColors.textSecondary),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(title, style: OmiType.callout)),
                Text(value, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                SizedBox(
                  width: 26,
                  child: onTap == null ? null : Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// --- Same person ---------------------------------------------------------------------------

class _SamePersonDetail extends StatelessWidget {
  const _SamePersonDetail({required this.item, required this.onDone});

  final ReviewItem item;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final pair = item.samePerson!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _EntityColumn(summary: pair.left)),
              const SizedBox(width: OmiSpacing.xs),
              Expanded(child: _EntityColumn(summary: pair.right)),
            ],
          ),
        ),
        if (pair.reason != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.sm, OmiSpacing.xxs, 0),
            child: Text(pair.reason!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ),
        const SizedBox(height: OmiSpacing.md),
        OmiButton(
          key: const Key('review_same_person_yes'),
          label: l10n.reviewYesMerge,
          expand: true,
          onPressed: () => _send(context, item, const ReviewAnswer.samePerson(true), onDone),
        ),
        const SizedBox(height: OmiSpacing.xs),
        Row(
          children: [
            Expanded(
              child: OmiButton.secondary(
                label: l10n.no,
                onPressed: () => _send(context, item, const ReviewAnswer.samePerson(false), onDone),
              ),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(
              child: OmiButton.secondary(
                label: l10n.reviewNotSure,
                onPressed: () => _send(context, item, const ReviewAnswer.notSure(), onDone),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _EntityColumn extends StatelessWidget {
  const _EntityColumn({required this.summary});

  final EntitySummary summary;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final lines = [
      if (summary.conversationCount > 0)
        (Icons.chat_bubble_outline, l10n.reviewConversationCount(summary.conversationCount)),
      for (final signal in summary.signals) (Icons.check, signal),
    ];
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 14),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          EntityInitialAvatar(name: summary.name, type: summary.type, size: 40),
          const SizedBox(height: 10),
          Text(
            summary.subtitle == null ? summary.name : '${summary.name} · ${summary.subtitle}',
            style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          for (final (icon, text) in lines)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  Icon(icon, size: 14, color: OmiColors.textSecondary),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

// --- Spelling ------------------------------------------------------------------------------

class _SpellingDetail extends StatefulWidget {
  const _SpellingDetail({required this.item, required this.onDone});

  final ReviewItem item;
  final VoidCallback onDone;

  @override
  State<_SpellingDetail> createState() => _SpellingDetailState();
}

class _SpellingDetailState extends State<_SpellingDetail> {
  String? _selected;
  final _custom = TextEditingController();

  @override
  void dispose() {
    _custom.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final spelling = widget.item.spelling!;
    final value = _custom.text.trim().isNotEmpty ? _custom.text.trim() : _selected;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (spelling.context != null) ...[
          ReviewSpellingContext(context: spelling.context!),
          const SizedBox(height: OmiSpacing.md),
        ] else if (widget.item.quote != null) ...[
          _EvidenceBox(children: [Text('“${widget.item.quote}”', style: OmiType.callout)]),
          const SizedBox(height: OmiSpacing.md),
        ],
        Wrap(
          spacing: OmiSpacing.xs,
          runSpacing: OmiSpacing.xs,
          children: [
            for (final option in spelling.options)
              ReviewAnswerPill(
                label: option,
                primary: _selected == option && _custom.text.trim().isEmpty,
                onPressed: () => setState(() {
                  _selected = option;
                  _custom.clear();
                }),
              ),
          ],
        ),
        if (spelling.allowCustom) ...[
          const SizedBox(height: OmiSpacing.sm),
          TextField(
            controller: _custom,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(labelText: l10n.reviewSpellingCustom),
          ),
        ],
        _Actions(
          primary: OmiButton(
            label: l10n.save,
            onPressed:
                value == null ? null : () => _send(context, widget.item, ReviewAnswer.spelling(value), widget.onDone),
          ),
          secondary: [
            OmiButton.secondary(
              label: l10n.reviewNotSure,
              onPressed: () => _send(context, widget.item, const ReviewAnswer.notSure(), widget.onDone),
            ),
          ],
        ),
      ],
    );
  }
}

// --- Dream suggestion ----------------------------------------------------------------------

class _ProposalDetail extends StatelessWidget {
  const _ProposalDetail({required this.item, required this.onDone});

  final ReviewItem item;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final proposal = item.agentProposal!;
    final reason = proposal.reason;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (proposal.before.isNotEmpty || proposal.after.isNotEmpty) ...[
          _EvidenceBox(
            children: [
              if (proposal.before.isNotEmpty) _ProposalValue(label: l10n.current, value: proposal.before),
              if (proposal.before.isNotEmpty && proposal.after.isNotEmpty) const SizedBox(height: OmiSpacing.sm),
              if (proposal.after.isNotEmpty) _ProposalValue(label: l10n.reviewProposalSuggested, value: proposal.after),
            ],
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
        if (reason != null) Text(reason, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
        _Actions(
          primary: OmiButton(
            label: l10n.reviewProposalApply,
            onPressed: () => _send(context, item, const ReviewAnswer.acceptProposal(), onDone),
          ),
          secondary: [
            OmiButton.secondary(
              label: l10n.dismiss,
              onPressed: () => _send(context, item, const ReviewAnswer.dismissProposal(), onDone),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.xs),
          child: OmiButton.secondary(
            label: l10n.reviewNotSure,
            onPressed: () => _send(context, item, const ReviewAnswer.notSure(), onDone),
          ),
        ),
      ],
    );
  }
}

class _ProposalValue extends StatelessWidget {
  const _ProposalValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary),
        ),
        const SizedBox(height: 3),
        Text(value, style: OmiType.callout),
      ],
    );
  }
}
