import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// "Help Omi recognize voices": a small daily set of short clips from the last
/// 48 hours. Each answer teaches Omi the owner's voice or a named person's voice.
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
        if (!provider.visible) return const SizedBox.shrink();
        return VisibilityDetector(
          key: const Key('speaker_tag_prompt_card_visibility'),
          onVisibilityChanged: (info) {
            if (info.visibleFraction > 0.5) provider.reportShown();
          },
          child: Container(
            key: const Key('speaker_tag_prompt_card'),
            decoration: const BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: BorderRadius.all(Radius.circular(OmiRadius.xl)),
            ),
            margin: const EdgeInsets.fromLTRB(16, 15, 16, 0),
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Header(provider: provider),
                const SizedBox(height: 12),
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: provider.finished ? _Finished(provider: provider) : _Question(provider: provider),
                ),
                if (provider.firstTime) ...[
                  const SizedBox(height: 12),
                  const Divider(color: OmiColors.border, height: 1),
                  const SizedBox(height: 8),
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
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: Icon(Icons.record_voice_over, color: Colors.white, size: 22),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.speakerTagPromptTitle,
                style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 2),
              Text(
                context.l10n.speakerTagPromptSubtitle,
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
            ],
          ),
        ),
        IconButton(
          key: const Key('speaker_tag_prompt_close'),
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.close, color: OmiColors.textSecondary, size: 20),
          tooltip: context.l10n.close,
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
        Expanded(
          child: Text(context.l10n.speakerTagPromptThanks, style: OmiType.subhead),
        ),
        TextButton(
          key: const Key('speaker_tag_prompt_done'),
          onPressed: provider.close,
          child: Text(context.l10n.done),
        ),
      ],
    );
  }
}

class _Question extends StatelessWidget {
  const _Question({required this.provider});

  final SpeakerTagPromptsProvider provider;

  @override
  Widget build(BuildContext context) {
    final prompt = provider.current!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ClipRow(provider: provider, prompt: prompt),
        if (provider.clipErrorPromptId == prompt.id) ...[
          const SizedBox(height: 6),
          Text(
            context.l10n.speakerTagPromptClipUnavailable,
            style: OmiType.footnote.copyWith(color: OmiColors.danger),
          ),
        ],
        const SizedBox(height: 14),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Expanded(child: Text(_question(context, prompt), style: OmiType.headline)),
            if (provider.prompts.length > 1)
              Text(
                context.l10n.speakerTagPromptProgress(provider.index + 1, provider.prompts.length),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              ),
          ],
        ),
        const SizedBox(height: 10),
        _Answers(provider: provider, prompt: prompt),
        if (provider.answerFailed) ...[
          const SizedBox(height: 8),
          Text(
            context.l10n.speakerTagPromptAnswerFailed,
            style: OmiType.footnote.copyWith(color: OmiColors.danger),
          ),
        ],
      ],
    );
  }

  String _question(BuildContext context, GeneratedSpeakerTagPrompt prompt) {
    switch (prompt.kind) {
      case 'confirm_person':
        final name = prompt.suggestedPersonName;
        return name == null || name.isEmpty
            ? context.l10n.speakerTagPromptWhoIsThis
            : context.l10n.speakerTagPromptIsThisPerson(name);
      case 'identify':
        return context.l10n.speakerTagPromptWhoIsThis;
      default:
        return context.l10n.speakerTagPromptIsThisYou;
    }
  }
}

class _ClipRow extends StatelessWidget {
  const _ClipRow({required this.provider, required this.prompt});

  final SpeakerTagPromptsProvider provider;
  final GeneratedSpeakerTagPrompt prompt;

  @override
  Widget build(BuildContext context) {
    final playing = provider.playingPromptId == prompt.id;
    final started = prompt.conversationStartedAt?.toLocal();
    final meta = [
      if (prompt.conversationTitle.isNotEmpty) prompt.conversationTitle,
      if (started != null) formatChatTimestamp(started, context: context),
    ].join(' · ');
    return Row(
      children: [
        Semantics(
          button: true,
          label: context.l10n.speakerTagPromptPlayClip,
          child: InkWell(
            key: const Key('speaker_tag_prompt_play'),
            customBorder: const CircleBorder(),
            onTap: () => provider.togglePlay(prompt),
            child: Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
              child: Icon(playing ? Icons.stop_rounded : Icons.play_arrow_rounded, color: Colors.black, size: 28),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (prompt.excerpt.isNotEmpty)
                Text(
                  '“${prompt.excerpt}”',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.subhead.copyWith(fontStyle: FontStyle.italic),
                ),
              if (meta.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  meta,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _Answers extends StatelessWidget {
  const _Answers({required this.provider, required this.prompt});

  final SpeakerTagPromptsProvider provider;
  final GeneratedSpeakerTagPrompt prompt;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final enabled = !provider.submitting;
    final buttons = <Widget>[];

    void add(String key, String label, SpeakerTagAnswer answer, {bool primary = false, String? personId}) {
      buttons.add(
        _AnswerChip(
          key: Key('speaker_tag_prompt_answer_$key'),
          label: label,
          primary: primary,
          onPressed: enabled ? () => provider.answer(answer, personId: personId) : null,
        ),
      );
    }

    switch (prompt.kind) {
      case 'confirm_person':
        add('yes', l10n.yes, SpeakerTagAnswer.person, primary: true, personId: prompt.suggestedPersonId);
        add('no', l10n.no, SpeakerTagAnswer.someoneElse);
        add('me', l10n.speakerTagPromptThatsMe, SpeakerTagAnswer.me);
        break;
      case 'identify':
        add('me', l10n.speakerTagPromptThatsMe, SpeakerTagAnswer.me);
        for (final person in _suggestedPeople(context)) {
          add('person_${person.id}', person.name, SpeakerTagAnswer.person, personId: person.id);
        }
        buttons.add(
          _AnswerChip(
            key: const Key('speaker_tag_prompt_answer_someone_new'),
            label: l10n.speakerTagPromptSomeoneNew,
            icon: Icons.add,
            onPressed: enabled ? () => _askName(context) : null,
          ),
        );
        add('someone_else', l10n.speakerTagPromptDontKnow, SpeakerTagAnswer.someoneElse);
        break;
      default:
        add('me', l10n.speakerTagPromptThatsMe, SpeakerTagAnswer.me, primary: true);
        add('not_me', l10n.speakerTagPromptNotMe, SpeakerTagAnswer.notMe);
    }
    add('skip', l10n.speakerTagPromptNotSure, SpeakerTagAnswer.skip);
    return Wrap(spacing: 8, runSpacing: 8, children: buttons);
  }

  List<Person> _suggestedPeople(BuildContext context) {
    final people = context.watch<PeopleProvider>().people;
    final byId = {for (final person in people) person.id: person};
    return [
      for (final id in prompt.suggestedPersonIds ?? const <String>[])
        if (byId[id] != null) byId[id]!,
    ];
  }

  Future<void> _askName(BuildContext context) async {
    final name = await showDialog<String>(context: context, builder: (_) => const _NameDialog());
    if (name == null) return;
    await provider.answer(SpeakerTagAnswer.newPerson, name: name);
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
    final style = primary
        ? FilledButton.styleFrom(
            backgroundColor: Colors.white,
            foregroundColor: Colors.black,
            minimumSize: const Size(0, 44),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            shape: const StadiumBorder(),
          )
        : OutlinedButton.styleFrom(
            foregroundColor: Colors.white,
            side: const BorderSide(color: OmiColors.border),
            minimumSize: const Size(0, 44),
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            shape: const StadiumBorder(),
          );
    final child = icon == null
        ? Text(label)
        : Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 16), const SizedBox(width: 4), Text(label)]);
    return primary
        ? FilledButton(onPressed: onPressed, style: style, child: child)
        : OutlinedButton(onPressed: onPressed, style: style, child: child);
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
        Switch(
          key: const Key('speaker_tag_prompt_save_voices_switch'),
          value: provider.saveOtherVoiceProfiles,
          onChanged: (value) => provider.setSaveOtherVoiceProfiles(value, fromFirstPrompt: true),
        ),
      ],
    );
  }
}
