import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/people_clean_up_page.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/person_detail_page.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/pages/settings/widgets/ignored_voices_sheet.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/pages/settings/widgets/people_list.dart';
import 'package:omi/pages/settings/widgets/voice_profile_settings_section.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
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
    final classic = Scaffold(
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
    if (!iosSwiftUiEnabled) return classic;
    return _nativePeople(provider, classic, visible, selectable, selected, allSelected);
  }

  Widget _nativePeople(PeopleProvider provider, Widget classic, List<Person> visible, List<String> selectable,
      List<Person> selected, bool allSelected) {
    final l10n = context.l10n;
    final voice = context.watch<SpeakerTagPromptsProvider>();
    final selecting = provider.selecting;
    return IosNativeSurface(
        title: selecting ? l10n.selectedCount(selected.length) : l10n.people,
        fallback: classic,
        loading: provider.loading,
        failed: provider.loadFailed,
        empty: provider.people.isEmpty ? l10n.noPeopleYet : l10n.noMatchingPeople,
        nativeOwner: selecting ? null : const VoiceProfileSettingsSection(),
        onRefresh: (_) => provider.refresh(),
        search: (value) => _changeQuery(value as String),
        searchValue: _query,
        searchPlaceholder: l10n.peopleSearchPlaceholder,
        toolbar: [
          NativeRow('people_back', selecting ? l10n.cancel : l10n.back, symbol: selecting ? 'xmark' : 'chevron.left',
              action: (_) async {
            selecting ? provider.endSelection() : await Navigator.of(context).maybePop();
          }),
          if (selecting)
            NativeRow('people_select_all', allSelected ? l10n.deselectAll : l10n.selectAll,
                action: (_) => allSelected ? provider.deselectAll(selectable) : provider.selectAll(selectable))
          else ...[
            if (provider.people.isNotEmpty)
              NativeRow('people_select', l10n.selectOption, kind: 'menu', options: {
                'select': l10n.selectPeople,
                if (provider.cleanUpCandidates.isNotEmpty)
                  'cleanup': '${l10n.cleanUpEllipsis} · ${l10n.cleanUpUnsureCount(provider.cleanUpCandidates.length)}',
              }, action: (value) {
                if (value == 'cleanup') {
                  _openCleanUp();
                } else {
                  OmiHaptics.light();
                  provider.beginSelection();
                }
              }),
            NativeRow('people_add', l10n.addPerson,
                symbol: 'plus', action: (_) => showPersonNameDialog(context, provider)),
          ],
        ],
        sections: [
          ...nativePeopleSections(context, provider, visible,
              management: true, filter: _filter, query: _query, onFilterChanged: _changeFilter, onClearSearch: () {
            _clearQuery();
            _changeFilter(PeopleFilter.all);
          }, onCleanUp: _openCleanUp),
          if (!selecting)
            NativeSection(
                'voice_settings',
                [
                  NativeRow('voice_ask_to_tag', l10n.voiceSettingsAskToTag,
                      subtitle: l10n.voiceSettingsAskToTagSubtitle,
                      kind: 'toggle',
                      value: voice.speakerTagPromptsEnabled,
                      enabled: voice.settingsLoaded,
                      action: (value) => voice.setSpeakerTagPromptsEnabled(value as bool)),
                  NativeRow('voice_save_others', l10n.speakerTagPromptSaveVoicesTitle,
                      subtitle: l10n.voiceSettingsSaveOthersSubtitle,
                      kind: 'toggle',
                      value: voice.saveOtherVoiceProfiles,
                      enabled: voice.settingsLoaded,
                      action: (value) => voice.setSaveOtherVoiceProfiles(value as bool, fromFirstPrompt: false)),
                  NativeRow('voice_ignored', l10n.ignoredVoicesTitle,
                      subtitle: l10n.ignoredVoicesSubtitle,
                      kind: 'navigation',
                      action: (_) => showIgnoredVoicesSheet(context)),
                ],
                title: l10n.voiceRecognitionSettings),
        ]);
  }
}

/// The People list as native sections, shared by Settings → People and the People scope of global
/// search: the filter, the incomplete-stats note, the Pinned / Recent / Not Heard Yet groups and the
/// no-match state. [management] (Settings) adds Select to each row's menu, the Clean Up banner
/// ([onCleanUp]) and, while selecting, toggling rows and the delete action. Without it a row offers
/// Open, Pin, Why and Delete, with Pin on the leading swipe and Delete on the trailing one.
List<NativeSection> nativePeopleSections(
  BuildContext context,
  PeopleProvider provider,
  List<Person> visible, {
  required bool management,
  PeopleFilter filter = PeopleFilter.all,
  String query = '',
  ValueChanged<PeopleFilter>? onFilterChanged,
  VoidCallback? onClearSearch,
  VoidCallback? onCleanUp,
}) {
  final l10n = context.l10n;
  final selecting = management && provider.selecting;
  final selected = visible.where((p) => !p.pinned && provider.selectedIds.contains(p.id)).toList();
  final filterLabels = {
    PeopleFilter.all: l10n.filterAll,
    PeopleFilter.lowConfidence: l10n.peopleFilterLowConfidence,
    PeopleFilter.pinned: l10n.peopleFilterPinned,
    PeopleFilter.needsVoice: l10n.peopleFilterNeedsVoice,
    PeopleFilter.notHeard: l10n.peopleNotHeardYet,
  };
  final groups = <String, List<Person>>{};
  final hasStats = visible.any((person) => person.conversationCount != null);
  for (final person in visible) {
    final group = person.pinned
        ? 'pinned'
        : hasStats && person.lastHeardAt == null
            ? 'not_heard'
            : 'recent';
    (groups[group] ??= []).add(person);
  }
  for (final people in groups.values) {
    people.sort((a, b) {
      if (a.lastHeardAt != null && b.lastHeardAt != null) return b.lastHeardAt!.compareTo(a.lastHeardAt!);
      if (a.lastHeardAt != null) return -1;
      if (b.lastHeardAt != null) return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });
  }
  return [
    if (onFilterChanged != null)
      NativeSection('people_filters', [
        NativeRow('people_filter', l10n.filterAll,
            kind: 'choice',
            value: filter.name,
            options: {
              for (final entry in filterLabels.entries)
                entry.key.name:
                    '${entry.value} · ${l10n.peopleCount(provider.people.where((p) => matchesPeopleFilter(p, entry.key)).length)}'
            },
            action: (value) => onFilterChanged(PeopleFilter.values.byName(value as String)))
      ]),
    if (provider.statsTruncated)
      NativeSection('people_stats', [NativeRow('people_stats_incomplete', l10n.peopleStatsIncomplete, kind: 'label')]),
    if (management &&
        onCleanUp != null &&
        !selecting &&
        provider.cleanUpCandidates.length >= kCleanUpBannerMinimum &&
        filter == PeopleFilter.all &&
        query.trim().isEmpty)
      NativeSection('people_review', [
        NativeRow('people_cleanup', l10n.cleanUpTitle,
            subtitle: l10n.cleanUpLead(provider.cleanUpCandidates.length),
            kind: 'navigation',
            action: (_) => onCleanUp())
      ]),
    for (final group in ['pinned', 'recent', 'not_heard'])
      if (groups[group]?.isNotEmpty == true)
        NativeSection(
            'people_$group',
            [
              for (final person in groups[group]!)
                NativeRow('person_${person.id}', person.name,
                    kind: selecting ? 'toggle' : 'navigation',
                    value: selecting ? provider.selectedIds.contains(person.id) : null,
                    enabled: !selecting || !person.pinned,
                    symbol: person.pinned ? 'pin.fill' : 'person.crop.circle',
                    level: confidenceLevel(person.confidence),
                    subtitle: '${confidenceLabel(context, person.confidence)} · ${personReasonLine(context, person)}',
                    options: {
                      'open': l10n.open,
                      'pin': person.pinned ? l10n.unpinAction : l10n.pinAction,
                      'why': l10n.whyConfidenceMenu(confidenceLabel(context, person.confidence)),
                      if (management && !person.pinned) 'select': l10n.selectOption,
                      'delete': l10n.delete
                    },
                    swipeLeading: management ? const [] : const ['pin'],
                    swipeTrailing: management ? const [] : const ['delete'], action: (value) async {
                  if (selecting) {
                    provider.toggleSelected(person.id);
                    return;
                  }
                  switch (value) {
                    case 'pin':
                      await togglePersonPinned(context, provider, person);
                    case 'why':
                      await showPersonConfidenceSheet(context, person);
                    case 'select' when management:
                      provider.beginSelection(person.id);
                    case 'delete':
                      await confirmAndDeletePeople(context, provider, [person]);
                    default:
                      await routeToPage(context, PersonDetailPage(personId: person.id));
                  }
                })
            ],
            title: group == 'pinned'
                ? l10n.peopleFilterPinned
                : group == 'not_heard'
                    ? l10n.peopleNotHeardYet
                    : hasStats
                        ? l10n.peopleRecent
                        : '',
            footer: selecting && group == 'pinned' ? l10n.selectAllSkipsPinned : ''),
    if (selecting)
      NativeSection('people_delete', [
        NativeRow('people_delete_selected', l10n.delete,
            destructive: true,
            enabled: selected.isNotEmpty,
            action: (_) => confirmAndDeletePeople(context, provider, selected))
      ]),
    if (visible.isEmpty && !provider.loading && !provider.loadFailed)
      NativeSection('people_empty', [
        NativeRow('people_empty_label', provider.people.isEmpty ? l10n.noPeopleYet : l10n.noMatchingPeople,
            subtitle: provider.people.isEmpty ? l10n.createPersonHint : l10n.tryAdjustingFilter, kind: 'label'),
        if (provider.people.isNotEmpty && onClearSearch != null)
          NativeRow('people_clear_search', l10n.clearSearch, action: (_) => onClearSearch()),
      ]),
  ];
}
