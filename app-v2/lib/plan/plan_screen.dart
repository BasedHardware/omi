import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/plan/plan_grouping.dart';
import 'package:nooto_v2/plan/widgets/plan_action_sheet.dart';
import 'package:nooto_v2/plan/widgets/plan_filter_rail.dart';
import 'package:nooto_v2/plan/widgets/plan_pivot_picker.dart';
import 'package:nooto_v2/plan/widgets/plan_row.dart';
import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// App id for the Jira plugin in the Apps catalog. Centralized here so the
/// swipe-gating + write-action flows can't drift.
const String _jiraAppId = 'nooto-jira';

/// Tab 3: Plan — full list of open commitments. Single sticky header band
/// holding both the pivot pill (leading) and the filter chip rail (trailing),
/// separated by a 1pt hairline. Restoring the screen name as the AppBar
/// title and folding the pivot into the rail keeps chrome to ONE band while
/// still surfacing both the screen identity and the grouping control.
///
/// Writes (transition / snooze) are gated on
/// `AppsProvider.isTwoWaySyncEnabled` for the Jira app — when that's OFF,
/// swipe gestures are disabled outright rather than firing a 403 on every
/// drag.
class PlanScreen extends StatefulWidget {
  const PlanScreen({super.key});

  @override
  State<PlanScreen> createState() => _PlanScreenState();
}

class _PlanScreenState extends State<PlanScreen> {
  PlanFilter _filter = PlanFilter.all;
  late PlanPivot _pivot;

  /// Transient project filter set by tapping a project pill on a Jira chip.
  /// Cleared when the user taps the chip again or switches tabs (we hook
  /// into deactivate for the tab-switch case).
  String? _projectFilter;

  @override
  void initState() {
    super.initState();
    _pivot = PlanPivotPicker.loadSaved();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ActionItemsProvider>().kickOffIfNeeded();
    });
  }

  @override
  void deactivate() {
    // Clear transient project filter when the tab unmounts so re-entering
    // Plan starts clean. Permanent filter / pivot state persists via Hive
    // (pivot, owned by Shell) and via the lifetime of this State (filter).
    _projectFilter = null;
    super.deactivate();
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ActionItemsProvider>();
    final apps = context.watch<AppsProvider>();
    final twoWaySync = apps.isTwoWaySyncEnabled(_jiraAppId);
    final allItems = provider.items.where((i) => !i.completed).toList();

    if (provider.loading && !provider.ready) return const _Loading();

    final items = _applyFilters(allItems);

    final topInset = MediaQuery.of(context).padding.top + AppStyles.spacingS;
    return RefreshIndicator(
      onRefresh: () => provider.fetchAll(),
      color: AppColors.brandPrimary,
      backgroundColor: AppColors.backgroundSecondary,
      child: CustomScrollView(
        slivers: [
          SliverPadding(padding: EdgeInsets.only(top: topInset)),
          SliverPersistentHeader(
            pinned: true,
            delegate: _StickyFilterHeader(
              child: Container(
                color: AppColors.backgroundPrimary,
                child: PlanFilterRail(
                  selected: _filter,
                  onChanged: (f) => setState(() => _filter = f),
                  pivot: _pivot,
                  onPivotChanged: (p) async {
                    setState(() => _pivot = p);
                    await PlanPivotPicker.persist(p);
                  },
                  activeProjectFilter: _projectFilter,
                  onClearProjectFilter: () => setState(() => _projectFilter = null),
                ),
              ),
            ),
          ),
          if (items.isEmpty)
            const SliverFillRemaining(hasScrollBody: false, child: _EmptyState())
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(
                AppStyles.spacingL,
                AppStyles.spacingS,
                AppStyles.spacingL,
                AppStyles.spacingXL,
              ),
              sliver: _GroupsSliver(
                groups: PlanGrouping.group(items, pivot: _pivot),
                pivot: _pivot,
                onToggle: (id) async {
                  HapticFeedback.lightImpact();
                  await provider.complete(id);
                },
                onProjectTap: (project) {
                  setState(() => _projectFilter = _projectFilter == project ? null : project);
                },
                jiraSwipeEnabled: twoWaySync,
                onTransition: _onTransition,
                onSnooze: _onSnooze,
                onLongPress: (item) => _onLongPress(item, twoWaySync: twoWaySync),
              ),
            ),
        ],
      ),
    );
  }

  List<ActionItem> _applyFilters(List<ActionItem> items) {
    final now = DateTime.now();
    final cutoff = now.add(const Duration(hours: 24));
    return items.where((item) {
      // Transient project filter (additive on top of the chosen quick filter).
      if (_projectFilter != null) {
        final ext = item.externalSource;
        if (ext == null || ext.jiraProjectKey != _projectFilter) return false;
      }
      switch (_filter) {
        case PlanFilter.all:
          return true;
        case PlanFilter.stuck:
          // Only Jira items can be "stuck" — transcript items have no status.
          final days = item.externalSource?.daysAtStatus;
          return days != null && days >= 3;
        case PlanFilter.dueSoon:
          final due = item.dueAt;
          return due != null && due.isBefore(cutoff);
      }
    }).toList();
  }

  /// Swipe-right path. Single-action — picks a transition target, fires it.
  Future<void> _onTransition(ActionItem item) async {
    final ext = item.externalSource;
    if (ext == null) return;
    final options = _transitionOptionsFor(ext.jiraStatusType);
    if (options.isEmpty) return;
    final picked = await PlanActionSheet.show(
      context,
      transitions: options,
      // Snooze hidden on the swipe-transition path — that path is
      // single-purpose. The long-press path bundles both.
      snoozeAvailable: false,
    );
    if (picked is! PlanActionTransition || !mounted) return;
    final provider = context.read<ActionItemsProvider>();
    final ok = await provider.transition(item.id, toStatus: picked.toStatus);
    if (!mounted) return;
    if (!ok) _showActionError(provider.lastActionError);
  }

  /// Swipe-left path. Direct snooze, no sheet.
  Future<void> _onSnooze(ActionItem item) async {
    final provider = context.read<ActionItemsProvider>();
    final until = DateTime.now().add(const Duration(days: 1));
    final ok = await provider.snooze(item.id, snoozeUntil: until);
    if (!mounted) return;
    if (!ok) _showActionError(provider.lastActionError);
  }

  /// VoiceOver-friendly entry: long-press opens a single sheet with both
  /// directions surfaced (transition rows + Snooze 1 day) so assistive-tech
  /// users get parity with the swipe gestures in one action.
  Future<void> _onLongPress(ActionItem item, {required bool twoWaySync}) async {
    final ext = item.externalSource;
    if (ext == null) return;
    final transitions = _transitionOptionsFor(ext.jiraStatusType);
    final picked = await PlanActionSheet.show(
      context,
      transitions: twoWaySync ? transitions : const [],
      snoozeAvailable: twoWaySync,
    );
    if (picked == null || !mounted) return;
    final provider = context.read<ActionItemsProvider>();
    if (picked is PlanActionTransition) {
      final ok = await provider.transition(item.id, toStatus: picked.toStatus);
      if (!mounted) return;
      if (!ok) _showActionError(provider.lastActionError);
    } else if (picked is PlanActionSnooze) {
      final ok = await provider.snooze(item.id, snoozeUntil: DateTime.now().add(const Duration(days: 1)));
      if (!mounted) return;
      if (!ok) _showActionError(provider.lastActionError);
    }
  }

  void _showActionError(String? key) {
    final messenger = ScaffoldMessenger.of(context);
    final message = key == 'two_way_sync_disabled'
        ? 'Enable Jira write-back in Settings → Apps → Jira'
        : "Couldn't update Jira. Try again.";
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }
}

/// Available transitions per status_type. Hard-coded for now — the backend
/// can return per-issue available transitions later, but this matches what
/// most Jira projects expose by default and keeps the sheet selection
/// predictable.
List<String> _transitionOptionsFor(String? statusType) {
  switch (statusType) {
    case 'todo':
      return const ['In Progress', 'Done'];
    case 'indeterminate':
      return const ['In Review', 'Done'];
    case 'done':
      return const [];
    default:
      return const ['In Progress', 'Done'];
  }
}

/// Renders the grouped list. Wraps Jira rows in a [Dismissible] when
/// [jiraSwipeEnabled] is true; transcript rows render bare regardless.
class _GroupsSliver extends StatelessWidget {
  const _GroupsSliver({
    required this.groups,
    required this.pivot,
    required this.onToggle,
    required this.onProjectTap,
    required this.jiraSwipeEnabled,
    required this.onTransition,
    required this.onSnooze,
    required this.onLongPress,
  });

  final List<PlanGroup> groups;
  final PlanPivot pivot;
  final Future<void> Function(String id) onToggle;
  final ValueChanged<String> onProjectTap;
  final bool jiraSwipeEnabled;
  final Future<void> Function(ActionItem item) onTransition;
  final Future<void> Function(ActionItem item) onSnooze;
  final Future<void> Function(ActionItem item) onLongPress;

  @override
  Widget build(BuildContext context) {
    return SliverList.builder(
      itemCount: groups.length,
      itemBuilder: (_, i) => _GroupSection(
        title: groups[i].title,
        items: groups[i].items,
        pivot: pivot,
        onToggle: onToggle,
        onProjectTap: onProjectTap,
        jiraSwipeEnabled: jiraSwipeEnabled,
        onTransition: onTransition,
        onSnooze: onSnooze,
        onLongPress: onLongPress,
      ),
    );
  }
}

class _GroupSection extends StatelessWidget {
  const _GroupSection({
    required this.title,
    required this.items,
    required this.pivot,
    required this.onToggle,
    required this.onProjectTap,
    required this.jiraSwipeEnabled,
    required this.onTransition,
    required this.onSnooze,
    required this.onLongPress,
  });
  final String title;
  final List<ActionItem> items;
  final PlanPivot pivot;
  final Future<void> Function(String id) onToggle;
  final ValueChanged<String> onProjectTap;
  final bool jiraSwipeEnabled;
  final Future<void> Function(ActionItem item) onTransition;
  final Future<void> Function(ActionItem item) onSnooze;
  final Future<void> Function(ActionItem item) onLongPress;

  @override
  Widget build(BuildContext context) {
    // Per FINDING-103: drop the "From conversation" prefix on transcript
    // rows when the visible group is single-source (no Jira items). Six
    // rows in a row narrating the same source is noise — only useful when
    // there's a contrast.
    final hasJira = items.any((i) => i.externalSource?.source == 'jira');
    final hasTranscript = items.any((i) => i.externalSource == null);
    final mixed = hasJira && hasTranscript;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingXL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS),
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.textTertiary,
                letterSpacing: 0.8,
              ),
            ),
          ),
          const SizedBox(height: AppStyles.spacingS),
          for (final item in items)
            PlanRowSwipeWrapper(
              key: ValueKey(item.id),
              item: item,
              sectionHasMixedSources: mixed,
              pivot: pivot,
              onToggle: () => onToggle(item.id),
              onProjectTap: item.externalSource?.jiraProjectKey != null
                  ? () => onProjectTap(item.externalSource!.jiraProjectKey!)
                  : null,
              jiraSwipeEnabled: jiraSwipeEnabled,
              onTransition: () => onTransition(item),
              onSnooze: () => onSnooze(item),
              onLongPress: () => onLongPress(item),
            ),
        ],
      ),
    );
  }
}

/// Wraps a Jira row in a [Dismissible] when [jiraSwipeEnabled] is true, AND
/// adds a long-press handler that fires the parent's action sheet (parity
/// path for VoiceOver users). Transcript rows always render bare —
/// "mark done" lives on the checkbox tap.
///
/// Visibility: public-ish (`PlanRowSwipeWrapper`) because the wrapping
/// logic is the unit-test target. Production code routes through it via
/// `_GroupSection`; tests instantiate it directly to avoid spinning up the
/// full PlanScreen + HTTP fixtures.
class PlanRowSwipeWrapper extends StatelessWidget {
  const PlanRowSwipeWrapper({
    super.key,
    required this.item,
    required this.sectionHasMixedSources,
    required this.onToggle,
    required this.onProjectTap,
    required this.jiraSwipeEnabled,
    required this.onTransition,
    required this.onSnooze,
    required this.onLongPress,
    this.pivot = PlanPivot.byDate,
  });

  final ActionItem item;
  final bool sectionHasMixedSources;
  final Future<void> Function() onToggle;
  final VoidCallback? onProjectTap;
  final bool jiraSwipeEnabled;
  final Future<void> Function() onTransition;
  final Future<void> Function() onSnooze;
  final Future<void> Function() onLongPress;
  final PlanPivot pivot;

  @override
  Widget build(BuildContext context) {
    final ext = item.externalSource;
    final isJira = ext?.source == 'jira';
    final row = PlanRow(
      item: item,
      onToggle: onToggle,
      onProjectTap: onProjectTap,
      sectionHasMixedSources: sectionHasMixedSources,
      pivot: pivot,
    );
    if (!isJira) return row;

    // VoiceOver / long-press parity path. Available even when swipe is
    // disabled — the sheet itself gates available actions on
    // jiraSwipeEnabled.
    final withLongPress = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onLongPress: () {
        HapticFeedback.mediumImpact();
        onLongPress();
      },
      child: row,
    );

    if (!jiraSwipeEnabled) return withLongPress;

    return Semantics(
      hint: 'Long press for actions',
      child: Dismissible(
        key: ValueKey('jira-swipe-${item.id}'),
        background: const _SwipeBg(
          alignment: Alignment.centerLeft,
          color: AppColors.brandPrimary,
          icon: Icons.arrow_forward_rounded,
          label: 'Move…',
        ),
        secondaryBackground: const _SwipeBg(
          alignment: Alignment.centerRight,
          color: AppColors.backgroundTertiary,
          icon: Icons.access_time_rounded,
          label: 'Snooze 1d',
        ),
        confirmDismiss: (direction) async {
          if (direction == DismissDirection.startToEnd) {
            // "done" items have no transitions to offer — bounce back.
            if (ext?.jiraStatusType == 'done') return false;
            await onTransition();
          } else if (direction == DismissDirection.endToStart) {
            await onSnooze();
          }
          // Always return false — the swipe is a gesture trigger, the row
          // stays in place.
          return false;
        },
        child: withLongPress,
      ),
    );
  }
}

/// Background revealed during a Dismissible drag. Color-coded per
/// direction; icon + short label describe the eventual action.
class _SwipeBg extends StatelessWidget {
  const _SwipeBg({required this.alignment, required this.color, required this.icon, required this.label});

  final Alignment alignment;
  final Color color;
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final isLeading = alignment == Alignment.centerLeft;
    return Container(
      color: color,
      alignment: alignment,
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL),
      child: PlanSwipeLabel(label: label, icon: icon, leading: isLeading),
    );
  }
}

/// Header delegate for the sticky filter rail. The rail itself owns its
/// height; this delegate just pins it under the AppBar inset.
class _StickyFilterHeader extends SliverPersistentHeaderDelegate {
  const _StickyFilterHeader({required this.child});
  final Widget child;

  static const double _railHeight = AppStyles.touchTargetMinimum + AppStyles.spacingS;

  @override
  double get minExtent => _railHeight;

  @override
  double get maxExtent => _railHeight;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) => child;

  @override
  bool shouldRebuild(covariant _StickyFilterHeader oldDelegate) => oldDelegate.child != child;
}

class _Loading extends StatelessWidget {
  const _Loading();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: SizedBox(
        width: 28,
        height: 28,
        child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.brandPrimary),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_outline_rounded, size: 32, color: AppColors.textTertiary),
            SizedBox(height: AppStyles.spacingM),
            Text(
              'Nothing pending.',
              style: TextStyle(fontSize: 17, color: AppColors.textPrimary, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: AppStyles.spacingXS),
            Text(
              "I'll surface commitments here as they come up in conversations.",
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: AppColors.textTertiary, height: 1.4),
            ),
          ],
        ),
      ),
    );
  }
}
