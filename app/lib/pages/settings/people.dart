import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/settings/person_detail_page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/voice_profile_settings_section.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/functions.dart';

enum PeopleFilter { all, needsVoice, notHeard }

/// A person whose voice Omi cannot recognize and is not already processing.
bool personNeedsVoice(Person p) => p.voiceReadiness != 'ready' && p.voiceReadiness != 'saved_sample_awaiting_embedding';

class UserPeoplePage extends StatefulWidget {
  const UserPeoplePage({super.key});

  @override
  State<UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<UserPeoplePage> {
  final _search = TextEditingController();
  String _query = '';
  PeopleFilter _filter = PeopleFilter.all;

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

  /// Confirms, then deletes. True when every person was deleted; a failure stays in the list.
  Future<bool> _delete(PeopleProvider provider, List<Person> people) async {
    if (people.isEmpty || !await _confirmDelete(people)) return false;
    final deleted = await provider.deletePeople(people.map((p) => p.id).toList());
    final ok = deleted == people.length;
    ok ? OmiHaptics.success() : OmiHaptics.error();
    if (!ok && mounted) OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
    return ok;
  }

  void _openPerson(Person person) => routeToPage(context, PersonDetailPage(personId: person.id));

  void _beginSelection(PeopleProvider provider, [String? personId]) {
    OmiHaptics.light();
    provider.beginSelection(personId);
  }

  void _toggle(PeopleProvider provider, Person person) {
    OmiHaptics.selection();
    provider.toggleSelected(person.id);
  }

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
          onSelected: () => _beginSelection(provider, person.id),
        ),
        OmiMenuAction(
          icon: Icons.delete_outline,
          label: l10n.delete,
          isDestructive: true,
          onSelected: () => _delete(provider, [person]),
        ),
      ],
    );
  }

  bool _matches(Person p, PeopleFilter filter) => switch (filter) {
        PeopleFilter.all => true,
        PeopleFilter.needsVoice => personNeedsVoice(p),
        PeopleFilter.notHeard => p.conversationCount != null && p.lastHeardAt == null,
      };

  /// Heard people first (newest first), then those with no conversations. Without stats (offline
  /// cache) it is a single list by name.
  List<Person> _visible(PeopleProvider provider) {
    final q = _query.trim().toLowerCase();
    final list =
        provider.people.where((p) => (q.isEmpty || p.name.toLowerCase().contains(q)) && _matches(p, _filter)).toList();
    list.sort((a, b) {
      final ah = a.lastHeardAt, bh = b.lastHeardAt;
      if (ah != null && bh != null) return bh.compareTo(ah);
      if (ah != null) return -1;
      if (bh != null) return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });
    return list;
  }

  void _clearFilters() {
    _search.clear();
    setState(() {
      _query = '';
      _filter = PeopleFilter.all;
    });
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
    final motion = OmiMotion.of(context);
    final people = _visible(provider);
    final selecting = provider.selecting;
    final allSelected = people.isNotEmpty && people.every((p) => provider.selectedIds.contains(p.id));
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
              key: const Key('people_select_all'),
              label: allSelected ? l10n.deselectAll : l10n.selectAll,
              onPressed: () {
                OmiHaptics.selection();
                allSelected ? provider.beginSelection() : provider.selectAll(people.map((p) => p.id));
              },
            )
          else ...[
            if (provider.people.isNotEmpty)
              OmiButton.toolbar(
                key: const Key('people_select'),
                label: l10n.selectOption,
                onPressed: () => _beginSelection(provider),
              ),
            OmiIconButton(
              icon: const Icon(Icons.add),
              label: l10n.addPerson,
              onPressed: () => showPersonNameDialog(context, provider),
            ),
          ],
        ],
      ),
      bottomNavigationBar: AnimatedSwitcher(
        duration: motion.standard,
        transitionBuilder: (child, animation) => SizeTransition(sizeFactor: animation, child: child),
        child: selecting
            ? SafeArea(
                key: const ValueKey('people_delete_bar'),
                child: Padding(
                  padding: const EdgeInsets.all(OmiSpacing.md),
                  child: OmiButton.destructive(
                    key: const Key('people_delete_selected'),
                    label: l10n.delete,
                    icon: Icons.delete_outline,
                    expand: true,
                    onPressed: provider.selectedIds.isEmpty
                        ? null
                        // Not awaited: the button should not spin behind the confirmation.
                        : () {
                            _delete(
                                provider, provider.people.where((p) => provider.selectedIds.contains(p.id)).toList());
                          },
                  ),
                ),
              )
            : const SizedBox.shrink(),
      ),
      body: _body(context, provider, people),
    );
  }

  Widget _body(BuildContext context, PeopleProvider provider, List<Person> people) {
    final l10n = context.l10n;
    if (provider.people.isEmpty) {
      if (provider.loading) return const OmiLoadingState();
      if (provider.loadFailed) {
        return OmiErrorState(message: l10n.somethingWentWrongTryAgain, onRetry: provider.initialize);
      }
      return OmiEmptyState(
        icon: Icons.people_outline,
        title: l10n.noPeopleYet,
        message: l10n.createPersonHint,
        action: OmiButton(
          label: l10n.addPerson,
          icon: Icons.add,
          size: OmiButtonSize.compact,
          onPressed: () => showPersonNameDialog(context, provider),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: provider.refresh,
      child: ListView(
        padding: EdgeInsets.fromLTRB(
            OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
        children: [
          OmiSearchField(
            placeholder: l10n.peopleSearchPlaceholder,
            controller: _search,
            onChanged: (value) => setState(() => _query = value),
            onCleared: () => setState(() => _query = ''),
          ),
          _filters(provider),
          const SizedBox(height: OmiSpacing.xs),
          if (people.isEmpty)
            OmiEmptyState(
              icon: Icons.search_off,
              title: l10n.noMatchingPeople,
              message: l10n.tryAdjustingFilter,
              action: OmiButton.secondary(
                label: l10n.clearSearch,
                size: OmiButtonSize.compact,
                onPressed: _clearFilters,
              ),
            ),
          ..._groups(people, provider),
          if (!provider.selecting) ...[
            const SizedBox(height: OmiSpacing.lg),
            const VoiceProfileSettingsSection(),
          ],
        ],
      ),
    );
  }

  /// All / Needs Voice / Not Heard Yet, each with its count. Only drawn when stats have loaded and
  /// at least one filter would narrow the list.
  Widget _filters(PeopleProvider provider) {
    final l10n = context.l10n;
    final all = provider.people;
    if (all.every((p) => p.conversationCount == null)) return const SizedBox.shrink();
    final counts = {for (final f in PeopleFilter.values) f: all.where((p) => _matches(p, f)).length};
    final labels = {
      PeopleFilter.all: l10n.filterAll,
      PeopleFilter.needsVoice: l10n.peopleFilterNeedsVoice,
      PeopleFilter.notHeard: l10n.peopleNotHeardYet,
    };
    final useful = [PeopleFilter.needsVoice, PeopleFilter.notHeard].where((f) => counts[f]! > 0).toList();
    if (useful.isEmpty && _filter == PeopleFilter.all) return const SizedBox.shrink();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.only(top: OmiSpacing.xxs),
      child: Row(
        children: [
          for (final f in [
            PeopleFilter.all,
            ...useful,
            if (_filter != PeopleFilter.all && !useful.contains(_filter)) _filter
          ])
            Padding(
              padding: const EdgeInsets.only(right: OmiSpacing.xs),
              child: OmiFilterChip(
                key: Key('people_filter_${f.name}'),
                label: labels[f]!,
                count: counts[f],
                semanticsLabel: '${labels[f]}, ${l10n.peopleCount(counts[f]!)}',
                selected: _filter == f,
                onSelected: () => setState(() => _filter = f),
              ),
            ),
        ],
      ),
    );
  }

  List<Widget> _groups(List<Person> people, PeopleProvider provider) {
    final l10n = context.l10n;
    final hasStats = people.any((p) => p.conversationCount != null);
    final groups = <String, List<Person>>{};
    for (final person in people) {
      final group = !hasStats || _filter == PeopleFilter.notHeard
          ? ''
          : person.lastHeardAt != null
              ? l10n.peopleRecent
              : l10n.peopleNotHeardYet;
      groups.putIfAbsent(group, () => []).add(person);
    }
    return [
      for (final MapEntry(key: title, value: members) in groups.entries) ...[
        const SizedBox(height: OmiSpacing.sm),
        if (title.isNotEmpty) ...[const SizedBox(height: OmiSpacing.xs), OmiSectionHeader(title)],
        _card([
          for (final person in members)
            _PersonRow(
              key: ValueKey(person.id),
              person: person,
              selecting: provider.selecting,
              selected: provider.selectedIds.contains(person.id),
              onTap: () => provider.selecting ? _toggle(provider, person) : _openPerson(person),
              onLongPress: () => provider.selecting ? _toggle(provider, person) : _showRowMenu(person, provider),
              onSwipeDelete: () => _delete(provider, [person]),
            ),
        ]),
      ],
    ];
  }

  /// Rows in one rounded card, with hairlines inset past the avatar.
  Widget _card(List<Widget> rows) {
    return ClipRRect(
      borderRadius: OmiRadius.lgAll,
      child: Material(
        color: OmiColors.surface1,
        child: Column(
          children: [
            for (final (i, row) in rows.indexed) ...[
              if (i > 0) Divider(height: 1, thickness: 1, indent: 72, color: OmiColors.border),
              row,
            ],
          ],
        ),
      ),
    );
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
    required this.onSwipeDelete,
  });

  final Person person;
  final bool selecting;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  /// Confirms and deletes; the row only leaves once the delete succeeded.
  final Future<bool> Function() onSwipeDelete;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final motion = OmiMotion.of(context);
    final heard = person.lastHeardAt;
    final count = person.conversationCount;
    final voice = l10n.voiceRecognitionStatus(person.voiceReadiness);
    // Heard: how much and how recently. Not heard (or no stats): what Omi knows of their voice.
    final subtitle = count != null && heard != null
        ? '${l10n.conversationCount(count)} · ${OmiDateFormat.of(context).dayHeader(heard)}'
        : voice;
    final row = Semantics(
      button: true,
      selected: selecting ? selected : null,
      label: subtitle == voice ? '${person.name}, $voice' : '${person.name}, $subtitle, $voice',
      child: InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        child: ExcludeSemantics(
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 68),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  AnimatedSize(
                    duration: motion.standard,
                    curve: OmiMotion.standardCurve,
                    child: selecting
                        ? Padding(
                            padding: const EdgeInsets.only(right: OmiSpacing.sm),
                            child: AnimatedSwitcher(
                              duration: motion.quick,
                              child: Icon(
                                selected ? Icons.check_circle : Icons.radio_button_unchecked,
                                key: ValueKey(selected),
                                color: selected ? OmiColors.accent : OmiColors.textTertiary,
                              ),
                            ),
                          )
                        : const SizedBox.shrink(),
                  ),
                  PersonAvatar(person: person),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          person.name,
                          style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          subtitle,
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  if (!selecting) Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    if (selecting) return row;
    return Dismissible(
      key: ValueKey('dismiss-${person.id}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) => onSwipeDelete(),
      background: Container(
        color: OmiColors.danger,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: OmiSpacing.lg),
        child: Icon(Icons.delete_outline, color: OmiPalette.dark.textPrimary),
      ),
      child: row,
    );
  }
}
