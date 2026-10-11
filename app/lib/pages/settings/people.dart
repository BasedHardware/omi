import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/people_clean_up_page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/pages/settings/widgets/voice_profile_settings_section.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/functions.dart';

/// Settings → Voice & People → People: the shared [PeopleList] with the management chrome — Select
/// (plain selection or Clean Up), Add, the Clean Up banner, and the Voice Recognition switches.
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

  void _openCleanUp() => routeToPage(context, const PeopleCleanUpPage());

  void _showSelectMenu(PeopleProvider provider) {
    final l10n = context.l10n;
    final unsure = provider.cleanUpCandidates.length;
    showOmiRowMenu(
      context,
      title: l10n.selectOption,
      actions: [
        OmiMenuAction(
          icon: Icons.check_circle_outline,
          label: l10n.selectPeople,
          onSelected: () {
            OmiHaptics.light();
            provider.beginSelection();
          },
        ),
        if (unsure > 0)
          OmiMenuAction(
            icon: Icons.people_outline,
            label: '${l10n.cleanUpEllipsis} · ${l10n.cleanUpUnsureCount(unsure)}',
            onSelected: _openCleanUp,
          ),
      ],
    );
  }

  void _clearQuery() {
    _search.clear();
    _changeQuery('');
  }

  void _changeQuery(String query) {
    final provider = context.read<PeopleProvider>();
    if (provider.selecting) provider.beginSelection();
    setState(() => _query = query);
  }

  void _changeFilter(PeopleFilter filter) {
    final provider = context.read<PeopleProvider>();
    if (provider.selecting) provider.beginSelection();
    setState(() => _filter = filter);
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
    final selecting = provider.selecting;
    final visible = visiblePeople(provider.people, _query, _filter);
    final selectable = visible.where((p) => !p.pinned).map((p) => p.id).toList();
    final selected = visible.where((p) => !p.pinned && provider.selectedIds.contains(p.id)).toList();
    final allSelected = selectable.isNotEmpty && selectable.every(provider.selectedIds.contains);
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: selecting
            ? OmiIconButton(icon: const Icon(Icons.close), label: l10n.cancel, onPressed: provider.endSelection)
            : const OmiBackButton(),
        title: Text(selecting ? l10n.selectedCount(selected.length) : l10n.people),
        actions: [
          if (selecting)
            OmiButton.tertiary(
              key: const Key('people_select_all'),
              size: OmiButtonSize.compact,
              label: allSelected ? l10n.deselectAll : l10n.selectAll,
              onPressed: () {
                OmiHaptics.selection();
                allSelected ? provider.deselectAll(selectable) : provider.selectAll(selectable);
              },
            )
          else ...[
            if (provider.people.isNotEmpty)
              OmiButton.tertiary(
                key: const Key('people_select'),
                size: OmiButtonSize.compact,
                label: l10n.selectOption,
                onPressed: () => _showSelectMenu(provider),
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
                    onPressed: selected.isEmpty
                        ? null
                        // Not awaited: the button should not spin behind the confirmation.
                        : () {
                            confirmAndDeletePeople(context, provider, selected);
                          },
                  ),
                ),
              )
            : const SizedBox.shrink(),
      ),
      body: PeopleList(
        query: _query,
        filter: _filter,
        onFilterChanged: _changeFilter,
        allowSelection: true,
        onCleanUp: _openCleanUp,
        onClearQuery: _clearQuery,
        emptyAction: OmiButton(
          label: l10n.addPerson,
          icon: Icons.add,
          size: OmiButtonSize.compact,
          onPressed: () => showPersonNameDialog(context, provider),
        ),
        leading: [
          if (provider.people.isNotEmpty)
            OmiSearchField(
              placeholder: l10n.peopleSearchPlaceholder,
              controller: _search,
              onChanged: _changeQuery,
              onCleared: () => _changeQuery(''),
            ),
        ],
        trailing: [
          if (!selecting) ...[const SizedBox(height: OmiSpacing.lg), const VoiceProfileSettingsSection()],
        ],
      ),
    );
  }
}
