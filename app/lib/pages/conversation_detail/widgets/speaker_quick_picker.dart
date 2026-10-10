import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Opens the one-tap picker that names the lines chosen in selection mode. [onPicked] gets the
/// person's id ('user' for the owner, '' for a new person) and name; the sheet closes when it
/// returns true.
Future<void> showSpeakerQuickPicker(
  BuildContext context, {
  required List<TranscriptSegment> segments,
  required bool Function(String personId, String personName) onPicked,
}) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.nameSpeakerTitle,
    builder: (_) => SpeakerQuickPicker(segments: segments, onPicked: onPicked),
  );
}

/// "You", then the people already named in this conversation, then the ones named most recently,
/// then everyone else by name; "Add Person" types a new name. One tap assigns — there is no Save.
class SpeakerQuickPicker extends StatefulWidget {
  const SpeakerQuickPicker({super.key, required this.segments, required this.onPicked});

  final List<TranscriptSegment> segments;
  final bool Function(String personId, String personName) onPicked;

  /// The picker's order: in this conversation (most lines first), then most recently used, then
  /// by name.
  static List<Person> order(List<Person> people, List<TranscriptSegment> segments, Map<String, int> lastUsedMs) {
    final lines = <String, int>{};
    for (final segment in segments) {
      final personId = segment.personId;
      if (!segment.isUser && personId != null) lines.update(personId, (count) => count + 1, ifAbsent: () => 1);
    }
    return [...people.where((person) => person.name.trim().isNotEmpty)]..sort((a, b) {
        final inA = lines[a.id] ?? 0;
        final inB = lines[b.id] ?? 0;
        if (inA != inB) return inB.compareTo(inA);
        final usedA = lastUsedMs[a.id] ?? 0;
        final usedB = lastUsedMs[b.id] ?? 0;
        if (usedA != usedB) return usedB.compareTo(usedA);
        return a.name.toLowerCase().compareTo(b.name.toLowerCase());
      });
  }

  @override
  State<SpeakerQuickPicker> createState() => _SpeakerQuickPickerState();
}

class _SpeakerQuickPickerState extends State<SpeakerQuickPicker> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _search = TextEditingController();
  bool _adding = false;

  @override
  void dispose() {
    _name.dispose();
    _search.dispose();
    super.dispose();
  }

  void _pick(String personId, String personName) {
    if (personId.isNotEmpty) {
      // Best-effort recency for the next picker; never blocks the label.
      try {
        SharedPreferencesUtil().speakerLabelLastUsedMs = {
          ...SharedPreferencesUtil().speakerLabelLastUsedMs,
          personId: DateTime.now().millisecondsSinceEpoch,
        };
      } catch (_) {}
    }
    if (widget.onPicked(personId, personName) && mounted) Navigator.pop(context);
  }

  String? _newNameProblem(List<Person> people) {
    final name = _name.text.trim();
    if (name.isEmpty) return null;
    if (name.toLowerCase() == SharedPreferencesUtil().givenName.trim().toLowerCase()) {
      return context.l10n.selectYouFromList;
    }
    if (people.any((person) => person.name.trim().toLowerCase() == name.toLowerCase())) {
      return context.l10n.personNameAlreadyExists;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final ordered = SpeakerQuickPicker.order(people, widget.segments, SharedPreferencesUtil().speakerLabelLastUsedMs);
    final query = _search.text.trim().toLowerCase();
    final visible = query.isEmpty ? ordered : ordered.where((p) => p.name.toLowerCase().contains(query)).toList();
    final problem = _newNameProblem(people);
    final newName = _name.text.trim();

    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_adding) ...[
            TextField(
              key: const Key('speaker_quick_picker_new_name'),
              controller: _name,
              autofocus: true,
              textCapitalization: TextCapitalization.words,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) {
                if (newName.isNotEmpty && problem == null) _pick('', newName);
              },
              decoration: InputDecoration(hintText: l10n.enterPersonsName, errorText: problem),
            ),
            const SizedBox(height: OmiSpacing.sm),
            Row(
              children: [
                OmiButton.tertiary(
                  label: l10n.cancel,
                  size: OmiButtonSize.compact,
                  onPressed: () => setState(() {
                    _adding = false;
                    _name.clear();
                  }),
                ),
                const Spacer(),
                OmiButton(
                  key: const Key('speaker_quick_picker_save_new'),
                  label: l10n.save,
                  size: OmiButtonSize.compact,
                  onPressed: newName.isEmpty || problem != null ? null : () => _pick('', newName),
                ),
              ],
            ),
          ] else ...[
            if (people.length > 10) ...[
              TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                decoration:
                    InputDecoration(hintText: l10n.searchPeople, prefixIcon: const Icon(Icons.search, size: 18)),
              ),
              const SizedBox(height: OmiSpacing.sm),
            ],
            Wrap(
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: [
                OmiFilterChip(
                  key: const Key('speaker_quick_picker_add'),
                  label: l10n.addPerson,
                  icon: Icons.add,
                  selected: false,
                  onSelected: () => setState(() => _adding = true),
                ),
                OmiFilterChip(
                  key: const Key('speaker_quick_picker_user'),
                  label: l10n.you,
                  selected: false,
                  onSelected: () => _pick('user', SharedPreferencesUtil().givenName),
                ),
                for (final person in visible)
                  OmiFilterChip(
                    key: Key('speaker_quick_picker_person_${person.id}'),
                    label: person.name,
                    selected: false,
                    onSelected: () => _pick(person.id, person.name),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
