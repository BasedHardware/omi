import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Review before a bulk delete: every Unverified, unpinned person starts ticked, each with the reason
/// Omi is unsure about them, so unticking is a judgment rather than a guess. Pinned people are never
/// listed. The delete confirms every time and cannot be undone.
class PeopleCleanUpPage extends StatefulWidget {
  const PeopleCleanUpPage({super.key});

  @override
  State<PeopleCleanUpPage> createState() => _PeopleCleanUpPageState();
}

class _PeopleCleanUpPageState extends State<PeopleCleanUpPage> {
  List<Person> get _candidates => context.read<PeopleProvider>().cleanUpCandidates;
  late final Set<String> _ticked = {for (final p in _candidates) p.id};

  void _toggle(Person person) {
    OmiHaptics.selection();
    setState(() => _ticked.contains(person.id) ? _ticked.remove(person.id) : _ticked.add(person.id));
  }

  Future<void> _delete() async {
    final provider = context.read<PeopleProvider>();
    final targets = _candidates.where((p) => _ticked.contains(p.id)).toList();
    // No spinner: the confirmation is the wait, and the button must not spin behind it.
    final ok = await confirmAndDeletePeople(context, provider, targets);
    if (ok && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    context.watch<PeopleProvider>();
    final l10n = context.l10n;
    final tickedCount = _candidates.where((p) => _ticked.contains(p.id)).length;
    final allTicked = _candidates.isNotEmpty && tickedCount == _candidates.length;
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(l10n.cleanUpTitle),
        actions: [
          if (_candidates.isNotEmpty)
            OmiButton.tertiary(
              key: const Key('people_clean_up_toggle_all'),
              size: OmiButtonSize.compact,
              label: allTicked ? l10n.deselectAll : l10n.selectAll,
              onPressed: () {
                OmiHaptics.selection();
                setState(() => allTicked ? _ticked.clear() : _ticked.addAll(_candidates.map((p) => p.id)));
              },
            ),
        ],
      ),
      bottomNavigationBar: _candidates.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(OmiSpacing.md),
                child: OmiButton.destructive(
                  key: const Key('people_clean_up_delete'),
                  label: tickedCount == 0 ? l10n.delete : l10n.deletePeopleCountAction(tickedCount),
                  icon: Icons.delete_outline,
                  expand: true,
                  // Not awaited: the button must not spin behind the confirmation.
                  onPressed: tickedCount == 0
                      ? null
                      : () {
                          _delete();
                        },
                ),
              ),
            ),
      body: _candidates.isEmpty
          ? OmiEmptyState(
              icon: Icons.check_circle_outline,
              title: l10n.cleanUpNothingTitle,
              message: l10n.cleanUpNothingMessage,
            )
          : ListView(
              padding: EdgeInsets.fromLTRB(
                OmiSpacing.md,
                OmiSpacing.xs,
                OmiSpacing.md,
                MediaQuery.paddingOf(context).bottom + OmiSpacing.xl,
              ),
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.xxs, OmiSpacing.sm),
                  child: Text(
                    l10n.cleanUpLead(_candidates.length),
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
                ClipRRect(
                  borderRadius: OmiRadius.lgAll,
                  child: Material(
                    color: OmiColors.surface1,
                    child: Column(
                      children: [
                        for (final (i, person) in _candidates.indexed) ...[
                          if (i > 0) Divider(height: 1, thickness: 1, indent: 108, color: OmiColors.border),
                          _ReviewRow(person: person, ticked: _ticked.contains(person.id), onTap: () => _toggle(person)),
                        ],
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
                  child: Text(l10n.cleanUpPinnedNote, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ),
              ],
            ),
    );
    return IosNativeSurface(
      title: l10n.cleanUpTitle,
      fallback: classic,
      toolbar: [
        NativeRow('cleanup_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
        if (_candidates.isNotEmpty)
          NativeRow('cleanup_select_all', allTicked ? l10n.deselectAll : l10n.selectAll, action: (_) {
            OmiHaptics.selection();
            setState(() => allTicked ? _ticked.clear() : _ticked.addAll(_candidates.map((person) => person.id)));
          }),
      ],
      sections: [
        if (_candidates.isEmpty)
          NativeSection('cleanup_empty', [
            NativeRow('cleanup_empty_label', l10n.cleanUpNothingTitle,
                subtitle: l10n.cleanUpNothingMessage, kind: 'label')
          ])
        else ...[
          NativeSection(
              'cleanup_candidates',
              [
                for (final person in _candidates)
                  NativeRow('cleanup_person_${person.id}', person.name,
                      kind: 'toggle',
                      value: _ticked.contains(person.id),
                      subtitle: personReasonLine(context, person),
                      level: confidenceLevel(person.confidence),
                      action: (_) => _toggle(person)),
              ],
              title: l10n.cleanUpLead(_candidates.length),
              footer: l10n.cleanUpPinnedNote),
          NativeSection('cleanup_actions', [
            NativeRow('cleanup_delete', tickedCount == 0 ? l10n.delete : l10n.deletePeopleCountAction(tickedCount),
                destructive: true, enabled: tickedCount > 0, action: (_) => _delete()),
          ]),
        ],
      ],
    );
  }
}

class _ReviewRow extends StatelessWidget {
  const _ReviewRow({required this.person, required this.ticked, required this.onTap});

  final Person person;
  final bool ticked;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final reason = personReasonLine(context, person);
    return Semantics(
      checked: ticked,
      label: '${person.name}, $reason',
      excludeSemantics: true,
      onTap: onTap,
      child: InkWell(
        key: Key('people_clean_up_row_${person.id}'),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 68),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: Row(
              children: [
                Icon(
                  ticked ? Icons.check_circle : Icons.radio_button_unchecked,
                  color: ticked ? OmiColors.accent : OmiColors.textTertiary,
                ),
                const SizedBox(width: OmiSpacing.sm),
                PersonAvatar(person: person, showVoiceBadge: false),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Opacity(
                    opacity: ticked ? 1 : 0.6,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(person.name, style: OmiType.body.copyWith(fontWeight: FontWeight.w500)),
                        const SizedBox(height: 3),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(top: 5),
                              child: PersonConfidenceMeter(person: person),
                            ),
                            const SizedBox(width: 7),
                            Expanded(
                              child: Text(reason, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
