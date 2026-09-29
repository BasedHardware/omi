import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/settings/person_detail_page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/pages/settings/widgets/voice_profile_settings_section.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/functions.dart';

class UserPeoplePage extends StatelessWidget {
  const UserPeoplePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _UserPeoplePage();
  }
}

class _UserPeoplePage extends StatefulWidget {
  const _UserPeoplePage();

  @override
  State<_UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<_UserPeoplePage> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    () {
      context.read<PeopleProvider>().initialize();
    }.withPostFrameCallback();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Deleting a person removes their samples too and cannot be undone: confirm every time.
  Future<bool> _confirmDelete(List<Person> people) {
    final l10n = context.l10n;
    return showOmiConfirm(
      context,
      title: people.length == 1 ? l10n.deletePersonTitle : l10n.deletePeopleTitle(people.length),
      message: people.length == 1 ? l10n.deletePersonConfirmation(people.first.name) : l10n.deletePeopleMessage,
      confirmLabel: l10n.delete,
      destructive: true,
    );
  }

  Future<void> _deleteSelected(PeopleProvider provider) async {
    final selected = provider.people.where((p) => provider.selectedIds.contains(p.id)).toList();
    if (selected.isEmpty || !await _confirmDelete(selected)) return;
    final deleted = await provider.deleteSelected();
    OmiHaptics.success();
    if (mounted && deleted < selected.length) OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
  }

  void _openPerson(Person person) => routeToPage(context, PersonDetailPage(personId: person.id));

  void _showRowMenu(Person person, PeopleProvider provider) {
    final l10n = context.l10n;
    showOmiRowMenu(
      context,
      title: person.name,
      actions: [
        OmiMenuAction(icon: Icons.person_outline, label: l10n.open, onSelected: () => _openPerson(person)),
        OmiMenuAction(
          icon: Icons.check_circle_outline,
          label: l10n.selectOption,
          onSelected: () => provider.beginSelection(person.id),
        ),
        OmiMenuAction(
          icon: Icons.delete_outline,
          label: l10n.delete,
          isDestructive: true,
          onSelected: () async {
            if (await _confirmDelete([person])) await provider.deletePeople([person.id]);
          },
        ),
      ],
    );
  }

  /// Heard people first (newest first), then those with no conversations. Without stats (offline
  /// cache) it is a single list by name.
  List<Person> _visible(PeopleProvider provider) {
    final q = _query.trim().toLowerCase();
    final list = provider.people.where((p) => q.isEmpty || p.name.toLowerCase().contains(q)).toList();
    list.sort((a, b) {
      final ah = a.lastHeardAt, bh = b.lastHeardAt;
      if (ah != null && bh != null) return bh.compareTo(ah);
      if (ah != null) return -1;
      if (bh != null) return 1;
      return a.name.compareTo(b.name);
    });
    return list;
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !context.watch<PeopleProvider>().selecting,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.read<PeopleProvider>().endSelection();
      },
      child: Consumer<PeopleProvider>(builder: (context, provider, child) => _scaffold(context, provider)),
    );
  }

  Widget _scaffold(BuildContext context, PeopleProvider provider) {
    final l10n = context.l10n;
    final people = _visible(provider);
    final selecting = provider.selecting;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: selecting
            ? OmiIconButton(icon: const Icon(Icons.close), label: l10n.cancel, onPressed: provider.endSelection)
            : const OmiBackButton(),
        title: Text(selecting ? l10n.selectedCount(provider.selectedIds.length) : l10n.people),
        actions: [
          if (selecting)
            OmiButton.toolbar(
              label: l10n.selectAll,
              onPressed: () => provider.selectAll(people.map((p) => p.id)),
            )
          else ...[
            if (provider.people.isNotEmpty)
              OmiButton.toolbar(label: l10n.selectOption, onPressed: provider.beginSelection),
            OmiIconButton(
              icon: const Icon(Icons.add),
              label: l10n.addPerson,
              onPressed: () => showPersonNameDialog(context, provider),
            ),
          ],
        ],
      ),
      bottomNavigationBar: selecting
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(OmiSpacing.md),
                child: OmiButton.destructive(
                  label: l10n.delete,
                  expand: true,
                  onPressed: provider.selectedIds.isEmpty ? null : () => _deleteSelected(provider),
                ),
              ),
            )
          : null,
      body: provider.loading && provider.people.isEmpty
          ? const OmiLoadingState()
          : provider.people.isEmpty
              ? OmiEmptyState(
                  icon: Icons.people_outline,
                  title: l10n.noPeopleYet,
                  message: l10n.createPersonHint,
                  action: OmiButton(
                    label: l10n.addPerson,
                    icon: Icons.add,
                    size: OmiButtonSize.compact,
                    onPressed: () => showPersonNameDialog(context, provider),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () async => provider.initialize(),
                  child: ListView(
                    padding: EdgeInsets.only(bottom: MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
                    children: [
                      if (!selecting) const VoiceProfileSettingsSection(),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
                        child: OmiSearchField(
                          placeholder: l10n.peopleSearchPlaceholder,
                          controller: _search,
                          onChanged: (value) => setState(() => _query = value),
                          onCleared: () => setState(() => _query = ''),
                        ),
                      ),
                      ..._rows(people, provider),
                    ],
                  ),
                ),
    );
  }

  List<Widget> _rows(List<Person> people, PeopleProvider provider) {
    final l10n = context.l10n;
    final hasStats = people.any((p) => p.conversationCount != null);
    final widgets = <Widget>[];
    var lastGroup = '';
    for (final person in people) {
      if (hasStats) {
        final group = person.lastHeardAt != null ? l10n.peopleRecent : l10n.peopleNotHeardYet;
        if (group != lastGroup) {
          lastGroup = group;
          widgets.add(OmiSectionHeader(group));
        }
      }
      widgets.add(
        _PersonRow(
          key: ValueKey(person.id),
          person: person,
          selecting: provider.selecting,
          selected: provider.selectedIds.contains(person.id),
          onTap: () => provider.selecting ? provider.toggleSelected(person.id) : _openPerson(person),
          onLongPress: () => provider.selecting ? provider.toggleSelected(person.id) : _showRowMenu(person, provider),
          confirmDelete: () => _confirmDelete([person]),
          onDeleted: () => provider.deletePeople([person.id]),
        ),
      );
    }
    return widgets;
  }
}

class _PersonRow extends StatelessWidget {
  const _PersonRow({
    super.key,
    required this.person,
    required this.selecting,
    required this.selected,
    required this.onTap,
    required this.onLongPress,
    required this.confirmDelete,
    required this.onDeleted,
  });

  final Person person;
  final bool selecting;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final Future<bool> Function() confirmDelete;
  final VoidCallback onDeleted;

  Color _voiceColor() => switch (person.voiceReadiness) {
        'ready' => OmiColors.success,
        'saved_sample_awaiting_embedding' => OmiColors.warning,
        _ => OmiColors.textTertiary,
      };

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final heard = person.lastHeardAt;
    final count = person.conversationCount;
    final subtitle = count == null
        ? l10n.voiceRecognitionStatus(person.voiceReadiness)
        : heard == null
            ? l10n.peopleNotHeardYet
            : '${l10n.conversationCount(count)} · ${OmiDateFormat.of(context).date(heard)}';
    final row = Semantics(
      selected: selected,
      child: InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 64),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
            child: Row(
              children: [
                if (selecting)
                  Padding(
                    padding: const EdgeInsets.only(right: OmiSpacing.sm),
                    child: Icon(
                      selected ? Icons.check_circle : Icons.radio_button_unchecked,
                      color: selected ? OmiColors.accent : OmiColors.textTertiary,
                    ),
                  ),
                CircleAvatar(
                  radius: 20,
                  backgroundColor: OmiColors.surface2,
                  child: Text(
                    person.name.isEmpty ? '?' : person.name.characters.first.toUpperCase(),
                    style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(person.name, style: OmiType.body.copyWith(fontWeight: FontWeight.w500), maxLines: 1),
                      Text(
                        subtitle,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                Semantics(
                  label: l10n.voiceRecognitionStatus(person.voiceReadiness),
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: _voiceColor(), shape: BoxShape.circle),
                  ),
                ),
                if (!selecting) Icon(Icons.chevron_right, color: OmiColors.textTertiary),
              ],
            ),
          ),
        ),
      ),
    );
    if (selecting) return row;
    return Dismissible(
      key: ValueKey('dismiss-${person.id}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) => confirmDelete(),
      onDismissed: (_) => onDeleted(),
      background: Container(
        color: OmiColors.danger,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: OmiSpacing.lg),
        child: Icon(Icons.delete_outline, color: OmiColors.onAccent),
      ),
      child: row,
    );
  }
}
