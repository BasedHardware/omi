import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/settings/person_detail_page.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/pages/settings/widgets/person_confidence.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

enum PeopleFilter { all, lowConfidence, pinned, needsVoice, notHeard }

/// A person whose voice Omi cannot recognize and is not already processing.
bool personNeedsVoice(Person p) => p.voiceReadiness != 'ready' && p.voiceReadiness != 'saved_sample_awaiting_embedding';

bool matchesPeopleFilter(Person p, PeopleFilter filter) => switch (filter) {
      PeopleFilter.all => true,
      PeopleFilter.lowConfidence => p.confidence == 'unverified' && !p.pinned,
      PeopleFilter.pinned => p.pinned,
      PeopleFilter.needsVoice => personNeedsVoice(p),
      PeopleFilter.notHeard => p.conversationCount != null && p.lastHeardAt == null,
    };

/// Clean Up is offered as a banner once this many unpinned people are Unverified.
const int kCleanUpBannerMinimum = 3;

/// Confirms, then deletes. A single pinned person gets a confirm that says so and names them; pinned
/// people are never part of a bulk delete. True when every person was deleted.
Future<bool> confirmAndDeletePeople(BuildContext context, PeopleProvider provider, List<Person> people) async {
  final l10n = context.l10n;
  final targets = people.length == 1 ? people : people.where((p) => !p.pinned).toList();
  if (targets.isEmpty) return false;
  final single = targets.length == 1 ? targets.first : null;
  final confirmed = await showOmiConfirm(
    context,
    title: single == null
        ? l10n.deletePeopleTitle(targets.length)
        : single.pinned
            ? l10n.deletePersonNamedTitle(single.name)
            : l10n.deletePersonTitle,
    message: single == null
        ? l10n.deletePeopleMessage
        : single.pinned
            ? l10n.deletePinnedPersonMessage(single.name)
            : l10n.deletePersonConfirmation(single.name),
    confirmLabel: single != null && single.pinned ? l10n.deleteNamedPerson(single.name) : l10n.delete,
    destructive: true,
  );
  if (!confirmed) return false;
  final deleted = await provider.deletePeople(targets.map((p) => p.id).toList(), allowPinned: single?.pinned == true);
  final ok = deleted == targets.length;
  ok ? OmiHaptics.success() : OmiHaptics.error();
  if (!context.mounted) return ok;
  if (!ok) {
    OmiFeedback.error(context, l10n.somethingWentWrongTryAgain);
  } else if (targets.length > 1) {
    OmiFeedback.confirm(context, l10n.peopleDeletedToast(deleted));
  }
  return ok;
}

/// Pins or unpins with a confirm toast; the provider rolls back and an error shows if the server refuses.
Future<void> togglePersonPinned(BuildContext context, PeopleProvider provider, Person person) async {
  final l10n = context.l10n;
  final pin = !person.pinned;
  OmiHaptics.light();
  final ok = await provider.setPinned(person.id, pin);
  if (!context.mounted) return;
  if (ok) {
    OmiFeedback.confirm(context, pin ? l10n.personPinnedToast(person.name) : l10n.personUnpinnedToast(person.name));
  } else {
    OmiFeedback.error(context, l10n.somethingWentWrongTryAgain);
  }
}

/// The one People list, hosted by Settings → People and by the People scope in global search.
///
/// Everything inside is shared: filter chips (only those that narrow the list), the Pinned / Recent /
/// Not Heard Yet groups, the row (meter, reason, pin glyph), leading swipe to pin, trailing swipe to
/// delete, the long-press menu, and tapping a row to push [PersonDetailPage]. Hosts add their own
/// chrome through [leading] and [trailing], decide whether selection and the Clean Up banner exist,
/// and own the search [query].
class PeopleList extends StatefulWidget {
  const PeopleList({
    super.key,
    required this.query,
    this.leading = const [],
    this.trailing = const [],
    this.allowSelection = false,
    this.onCleanUp,
    this.onClearQuery,
    this.emptyAction,
  });

  final String query;
  final List<Widget> leading;
  final List<Widget> trailing;

  /// Settings host: long-press offers Select, rows toggle while selecting, pinned rows show a pin.
  final bool allowSelection;

  /// Settings host: shows the Clean Up banner (at least [kCleanUpBannerMinimum] unsure people).
  final VoidCallback? onCleanUp;
  final VoidCallback? onClearQuery;

  /// The one action on the "No People Yet" state (Add Person), when the host can add.
  final Widget? emptyAction;

  @override
  State<PeopleList> createState() => _PeopleListState();
}

class _PeopleListState extends State<PeopleList> {
  PeopleFilter _filter = PeopleFilter.all;

  void _openPerson(Person person) => routeToPage(context, PersonDetailPage(personId: person.id));

  void _showRowMenu(Person person, PeopleProvider provider) {
    final l10n = context.l10n;
    showOmiRowMenu(
      context,
      title: person.name,
      actions: [
        OmiMenuAction(icon: Icons.person_outline, label: l10n.open, onSelected: () => _openPerson(person)),
        OmiMenuAction(
          icon: person.pinned ? Icons.push_pin : Icons.push_pin_outlined,
          label: person.pinned ? l10n.unpinAction : l10n.pinAction,
          onSelected: () => togglePersonPinned(context, provider, person),
        ),
        OmiMenuAction(
          icon: Icons.info_outline,
          label: l10n.whyConfidenceMenu(confidenceLabel(context, person.confidence)),
          onSelected: () => showPersonConfidenceSheet(context, person),
        ),
        if (widget.allowSelection && !person.pinned)
          OmiMenuAction(
            icon: Icons.check_circle_outline,
            label: l10n.selectOption,
            onSelected: () {
              OmiHaptics.light();
              provider.beginSelection(person.id);
            },
          ),
        OmiMenuAction(
          icon: Icons.delete_outline,
          label: l10n.delete,
          isDestructive: true,
          onSelected: () => confirmAndDeletePeople(context, provider, [person]),
        ),
      ],
    );
  }

  List<Person> _visible(PeopleProvider provider) {
    final q = widget.query.trim().toLowerCase();
    return provider.people
        .where((p) => (q.isEmpty || p.name.toLowerCase().contains(q)) && matchesPeopleFilter(p, _filter))
        .toList();
  }

  /// Heard people first (newest first), then those with no conversations, then by name.
  static int _byRecency(Person a, Person b) {
    final ah = a.lastHeardAt, bh = b.lastHeardAt;
    if (ah != null && bh != null) return bh.compareTo(ah);
    if (ah != null) return -1;
    if (bh != null) return 1;
    return a.name.toLowerCase().compareTo(b.name.toLowerCase());
  }

  void _clear() {
    widget.onClearQuery?.call();
    setState(() => _filter = PeopleFilter.all);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<PeopleProvider>();
    if (provider.people.isEmpty) {
      final Widget state;
      if (provider.loading) {
        state = const OmiLoadingState();
      } else if (provider.loadFailed) {
        state = OmiErrorState(message: l10n.somethingWentWrongTryAgain, onRetry: provider.initialize);
      } else {
        state = OmiEmptyState(
          icon: Icons.people_outline,
          title: l10n.noPeopleYet,
          message: l10n.createPersonHint,
          action: widget.emptyAction,
        );
      }
      return ListView(
        padding: EdgeInsets.fromLTRB(
            OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
        children: [...widget.leading, state, ...widget.trailing],
      );
    }
    final people = _visible(provider);
    final unsure = provider.cleanUpCandidates.length;
    final showBanner = widget.onCleanUp != null &&
        unsure >= kCleanUpBannerMinimum &&
        !provider.selecting &&
        _filter == PeopleFilter.all &&
        widget.query.trim().isEmpty;
    return RefreshIndicator(
      onRefresh: provider.refresh,
      child: ListView(
        padding: EdgeInsets.fromLTRB(
            OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, MediaQuery.paddingOf(context).bottom + OmiSpacing.xl),
        children: [
          ...widget.leading,
          _filters(provider),
          if (showBanner) _CleanUpBanner(count: unsure, onReview: widget.onCleanUp!),
          const SizedBox(height: OmiSpacing.xs),
          if (people.isEmpty)
            OmiEmptyState(
              icon: Icons.search_off,
              title: l10n.noMatchingPeople,
              message: l10n.tryAdjustingFilter,
              action: OmiButton.secondary(label: l10n.clearSearch, size: OmiButtonSize.compact, onPressed: _clear),
            ),
          ..._groups(people, provider),
          ...widget.trailing,
        ],
      ),
    );
  }

  /// Chips that narrow the list, each with its count. Only drawn when at least one would narrow it.
  Widget _filters(PeopleProvider provider) {
    final l10n = context.l10n;
    final all = provider.people;
    final hasStats = all.any((p) => p.conversationCount != null);
    final counts = {for (final f in PeopleFilter.values) f: all.where((p) => matchesPeopleFilter(p, f)).length};
    final labels = {
      PeopleFilter.all: l10n.filterAll,
      PeopleFilter.lowConfidence: l10n.peopleFilterLowConfidence,
      PeopleFilter.pinned: l10n.peopleFilterPinned,
      PeopleFilter.needsVoice: l10n.peopleFilterNeedsVoice,
      PeopleFilter.notHeard: l10n.peopleNotHeardYet,
    };
    final useful = [
      PeopleFilter.lowConfidence,
      PeopleFilter.pinned,
      if (hasStats) PeopleFilter.needsVoice,
      if (hasStats) PeopleFilter.notHeard,
    ].where((f) => counts[f]! > 0 && counts[f]! < all.length).toList();
    if (useful.isEmpty && _filter == PeopleFilter.all) return const SizedBox.shrink();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.only(top: OmiSpacing.xxs),
      child: Row(
        children: [
          for (final f in [
            PeopleFilter.all,
            ...useful,
            if (_filter != PeopleFilter.all && !useful.contains(_filter)) _filter,
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
    final selecting = widget.allowSelection && provider.selecting;
    final hasStats = people.any((p) => p.conversationCount != null);
    final pinned = people.where((p) => p.pinned).toList()..sort(_byRecency);
    final rest = people.where((p) => !p.pinned).toList()..sort(_byRecency);
    final recent = [
      for (final p in rest)
        if (!hasStats || p.lastHeardAt != null) p
    ];
    final notHeard = [
      for (final p in rest)
        if (hasStats && p.lastHeardAt == null) p
    ];
    final groups = <(String, String?, List<Person>, String?)>[
      if (pinned.isNotEmpty)
        (
          l10n.peopleFilterPinned,
          l10n.peoplePinnedCount(pinned.length),
          pinned,
          selecting ? l10n.selectAllSkipsPinned : null,
        ),
      if (recent.isNotEmpty) (hasStats ? l10n.peopleRecent : '', null, recent, null),
      if (notHeard.isNotEmpty) (l10n.peopleNotHeardYet, null, notHeard, null),
    ];
    return [
      for (final (title, meta, members, footer) in groups) ...[
        const SizedBox(height: OmiSpacing.sm),
        if (title.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.xs),
          OmiSectionHeader(
            title,
            trailing:
                meta == null ? null : Text(meta, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ),
        ],
        _card([
          for (final person in members)
            PersonRow(
              key: ValueKey(person.id),
              person: person,
              selecting: selecting,
              selected: selecting && provider.selectedIds.contains(person.id),
              onTap: () {
                if (!selecting) return _openPerson(person);
                if (person.pinned) return;
                OmiHaptics.selection();
                provider.toggleSelected(person.id);
              },
              onLongPress: () => selecting ? provider.toggleSelected(person.id) : _showRowMenu(person, provider),
              onSwipePin: () => togglePersonPinned(context, provider, person),
              onSwipeDelete: () => confirmAndDeletePeople(context, provider, [person]),
            ),
        ]),
        if (footer != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
            child: Text(footer, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ),
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

class _CleanUpBanner extends StatelessWidget {
  const _CleanUpBanner({required this.count, required this.onReview});

  final int count;
  final VoidCallback onReview;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.sm),
      child: Container(
        key: const Key('people_clean_up_banner'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xs),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
              child: Icon(Icons.people_outline, size: 20, color: OmiColors.textPrimary),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l10n.cleanUpUnsureCount(count), style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(l10n.cleanUpBannerBody, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  const SizedBox(height: OmiSpacing.xxs),
                  OmiButton(
                    key: const Key('people_clean_up_review'),
                    label: l10n.reviewAction,
                    size: OmiButtonSize.compact,
                    onPressed: onReview,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// One person: avatar, name (pin glyph when pinned), last heard, and on the second line the
/// confidence meter with the reason for it. Leading swipe pins, trailing swipe deletes (confirmed).
class PersonRow extends StatelessWidget {
  const PersonRow({
    super.key,
    required this.person,
    required this.selecting,
    required this.selected,
    required this.onTap,
    required this.onLongPress,
    required this.onSwipePin,
    required this.onSwipeDelete,
  });

  final Person person;
  final bool selecting;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final Future<void> Function() onSwipePin;

  /// Confirms and deletes; the row only leaves once the delete succeeded.
  final Future<bool> Function() onSwipeDelete;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final motion = OmiMotion.of(context);
    final heard = person.lastHeardAt;
    final reason = personReasonLine(context, person);
    final band = confidenceLabel(context, person.confidence);
    final lead = !selecting
        ? null
        : person.pinned
            ? Icon(Icons.push_pin, size: 20, color: OmiColors.textTertiary)
            : Icon(
                selected ? Icons.check_circle : Icons.radio_button_unchecked,
                key: ValueKey(selected),
                color: selected ? OmiColors.accent : OmiColors.textTertiary,
              );
    final row = Semantics(
      button: true,
      selected: selecting && !person.pinned ? selected : null,
      label: [
        person.name,
        if (person.pinned) l10n.peopleFilterPinned,
        l10n.confidenceMeterLabel(band),
        reason,
        if (selecting && person.pinned) l10n.pinnedNotSelectable,
      ].join(', '),
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
                    child: lead == null
                        ? const SizedBox.shrink()
                        : Padding(
                            padding: const EdgeInsets.only(right: OmiSpacing.sm),
                            child: AnimatedSwitcher(duration: motion.quick, child: lead),
                          ),
                  ),
                  PersonAvatar(person: person, showVoiceBadge: false),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            // The name takes whatever the date leaves; it only truncates when it must.
                            Expanded(
                              child: Row(
                                children: [
                                  Flexible(
                                    child: Text(
                                      person.name,
                                      style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  if (person.pinned && !selecting) ...[
                                    const SizedBox(width: OmiSpacing.xxs),
                                    Icon(Icons.push_pin, size: 13, color: OmiColors.textTertiary),
                                  ],
                                ],
                              ),
                            ),
                            const SizedBox(width: OmiSpacing.xs),
                            if (heard != null && !selecting)
                              Text(
                                OmiDateFormat.of(context).dayHeader(heard),
                                style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                              ),
                            if (!selecting) Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary),
                          ],
                        ),
                        const SizedBox(height: 3),
                        Row(
                          children: [
                            PersonConfidenceMeter(person: person),
                            const SizedBox(width: 7),
                            Expanded(
                              child: Text(
                                reason,
                                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
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
      direction: DismissDirection.horizontal,
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          await onSwipePin();
          return false; // Pinning keeps the row; it only moves groups.
        }
        return onSwipeDelete();
      },
      background: Container(
        color: OmiColors.accent,
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: OmiSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(person.pinned ? Icons.push_pin_outlined : Icons.push_pin, color: OmiColors.onAccent),
            Text(
              person.pinned ? l10n.unpinAction : l10n.pinAction,
              style: OmiType.footnote.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
      secondaryBackground: Container(
        color: OmiColors.danger,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: OmiSpacing.lg),
        child: Icon(Icons.delete_outline, color: OmiPalette.dark.textPrimary),
      ),
      child: row,
    );
  }
}
