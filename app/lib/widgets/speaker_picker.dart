import 'package:flutter/material.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One voice-match suggestion the picker lists apart from everyone: [matchLevel] (when the server
/// ranked it) drives the meter, [pinned] swaps the row icon for a pin.
class SpeakerPickerCandidate {
  const SpeakerPickerCandidate({
    required this.personId,
    required this.name,
    this.matchLevel,
    this.pinned = false,
  });

  final String personId;
  final String name;
  final int? matchLevel;
  final bool pinned;
}

/// What the picker returned: an existing person, a new name, "someone I don't know", the owner
/// ("That's Me") or not a person at all (a TV, a voice assistant).
class SpeakerPickerChoice {
  const SpeakerPickerChoice.person(String this.personId, this.displayName)
      : name = null,
        unknown = false,
        me = false,
        notAPerson = false;
  const SpeakerPickerChoice.newPerson(String this.name)
      : personId = null,
        displayName = null,
        unknown = false,
        me = false,
        notAPerson = false;
  const SpeakerPickerChoice.unknown()
      : personId = null,
        name = null,
        displayName = null,
        unknown = true,
        me = false,
        notAPerson = false;
  const SpeakerPickerChoice.me()
      : personId = null,
        name = null,
        displayName = null,
        unknown = false,
        me = true,
        notAPerson = false;
  const SpeakerPickerChoice.notAPerson()
      : personId = null,
        name = null,
        displayName = null,
        unknown = false,
        me = false,
        notAPerson = true;

  final String? personId;
  final String? name;
  final String? displayName;
  final bool unknown;
  final bool me;
  final bool notAPerson;
}

/// "Who Is It?": search; That's Me and Not a Person when [offerMeAndNotAPerson]; a new person; the
/// closest voices (without [excludePersonId]), then everyone A to Z. A typed name that already
/// belongs to a person returns that person instead of creating a duplicate.
Future<SpeakerPickerChoice?> showSpeakerPicker(
  BuildContext context, {
  String? title,
  required List<SpeakerPickerCandidate> candidates,
  required List<Person> people,
  String? excludePersonId,
  bool allowUnknown = true,
  bool offerMeAndNotAPerson = false,
}) {
  return showOmiSheet<SpeakerPickerChoice>(
    context: context,
    title: title ?? context.l10n.whoIsItTitle,
    builder: (sheetContext) => _SpeakerPicker(
      candidates: candidates.where((c) => c.personId != excludePersonId).toList(),
      // Optimistic placeholders are pre-reconciliation local ids the backend
      // would reject as person_id; the prompt-card caller filtered them the
      // same way before this became shared (mirror here so every caller is
      // covered, not just the one that remembered).
      people: people.where((p) => p.id != excludePersonId && !p.id.startsWith('optimistic-person:')).toList(),
      allowUnknown: allowUnknown,
      offerMeAndNotAPerson: offerMeAndNotAPerson,
    ),
  );
}

class _SpeakerPicker extends StatefulWidget {
  const _SpeakerPicker({
    required this.candidates,
    required this.people,
    required this.allowUnknown,
    required this.offerMeAndNotAPerson,
  });

  final List<SpeakerPickerCandidate> candidates;
  final List<Person> people;
  final bool allowUnknown;
  final bool offerMeAndNotAPerson;

  @override
  State<_SpeakerPicker> createState() => _SpeakerPickerState();
}

class _SpeakerPickerState extends State<_SpeakerPicker> {
  final _search = TextEditingController();
  String _query = '';
  bool _showAllEveryone = false;

  /// Everyone rows rendered before the "Show all N" expander, mirroring the
  /// tag-speaker sheet's bounded initial layout for large rosters.
  static const int _kEveryoneCap = 24;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _pick(SpeakerPickerChoice choice) => Navigator.of(context).pop(choice);

  /// The (id, name) this name already names, if any: people first, then candidates (the server
  /// may rank someone the cached people list has not caught up with).
  (String, String)? _existing(String name) {
    final lower = name.toLowerCase();
    for (final p in widget.people) {
      if (p.name.toLowerCase() == lower) return (p.id, p.name);
    }
    for (final c in widget.candidates) {
      if (c.name.toLowerCase() == lower) return (c.personId, c.name);
    }
    return null;
  }

  /// A new-person answer goes through here, so a name that belongs to an existing person selects
  /// that person instead of creating a duplicate.
  void _returnNamed(String rawName) {
    final name = rawName.trim();
    final existing = _existing(name);
    _pick(
      existing != null ? SpeakerPickerChoice.person(existing.$1, existing.$2) : SpeakerPickerChoice.newPerson(name),
    );
  }

  Future<void> _newPerson() async {
    final names = {
      for (final p in widget.people) p.name.toLowerCase(),
      for (final c in widget.candidates) c.name.toLowerCase(),
    };
    final name = await showDialog<String>(context: context, builder: (_) => _NameDialog(existingNames: names));
    if (name != null && mounted) _returnNamed(name);
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
    // Everyone is always bounded — roster and search results alike: at most
    // [_kEveryoneCap] rows render behind a "Show all N" expander, so neither
    // a large roster nor a broad query lays out every match on open or per
    // keystroke.
    final visibleEveryone = _showAllEveryone ? everyone : everyone.take(_kEveryoneCap).toList();
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
      child: ListView(
        padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
        children: [
          OmiSearchField(
            placeholder: l10n.peopleSearchPlaceholder,
            controller: _search,
            onChanged: (value) => setState(() => _query = value),
            onCleared: () => setState(() => _query = ''),
          ),
          const SizedBox(height: OmiSpacing.sm),
          if (widget.offerMeAndNotAPerson && q.isEmpty) ...[
            OmiSettingsGroup(
              children: [
                OmiSettingsRow(
                  key: const Key('speaker_picker_me'),
                  leading: const Icon(Icons.person_outline),
                  title: l10n.speakerTagPromptThatsMeAction,
                  onTap: () => _pick(const SpeakerPickerChoice.me()),
                ),
                OmiSettingsRow(
                  key: const Key('speaker_picker_not_a_person'),
                  leading: const Icon(Icons.tv_outlined),
                  title: l10n.speakerTagPromptNotAPerson,
                  onTap: () => _pick(const SpeakerPickerChoice.notAPerson()),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const Key('speaker_picker_new_person'),
                leading: const Icon(Icons.person_add_alt_outlined),
                title: canAdd ? l10n.addNamedPersonAction(q) : l10n.newPersonEllipsis,
                onTap: canAdd ? () => _returnNamed(q) : _newPerson,
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
                for (final p in visibleEveryone)
                  OmiSettingsRow(
                    key: Key('speaker_picker_person_${p.id}'),
                    title: p.name,
                    leading: PersonAvatar(person: p, size: 32, showVoiceBadge: false),
                    onTap: () => _pick(SpeakerPickerChoice.person(p.id, p.name)),
                  ),
                if (!_showAllEveryone && everyone.length > _kEveryoneCap)
                  OmiSettingsRow(
                    key: const Key('speaker_picker_show_all'),
                    title: l10n.showAllPeople(everyone.length),
                    leading: const Icon(Icons.unfold_more),
                    onTap: () => setState(() => _showAllEveryone = true),
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
  const _NameDialog({required this.existingNames});

  /// Lowercased names the new person must not collide with.
  final Set<String> existingNames;

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

  String? get _duplicateError {
    final name = _controller.text.trim().toLowerCase();
    if (name.isEmpty) return null;
    return widget.existingNames.contains(name) ? context.l10n.personNameAlreadyExists : null;
  }

  bool get _valid {
    final length = _controller.text.trim().length;
    return length >= 2 && length <= 40 && _duplicateError == null;
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
          decoration: InputDecoration(
            hintText: context.l10n.speakerTagPromptNameHint,
            errorText: _duplicateError,
          ),
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
