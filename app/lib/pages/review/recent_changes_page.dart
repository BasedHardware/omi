import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/review.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart';
import 'package:omi/pages/review/widgets/recent_change_groups.dart';
import 'package:omi/pages/review/widgets/recent_change_row.dart';
import 'package:omi/pages/review/widgets/recent_change_sheet.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

typedef ReviewChangesLoader = Future<ApiResult<ReviewChangesPage>> Function({String? cursor});
typedef ReviewChangeToggler = Future<ApiResult<ReviewChange>> Function(String changeId, {required bool undone});

/// What Omi changed on its own in the last 30 days, grouped by what changed. Each row shows the
/// change itself (before → after) and opens every place it landed, in context, with Undo. A
/// back-office screen reached from Review; nothing here is pushed at the user.
class RecentChangesPage extends StatefulWidget {
  const RecentChangesPage({super.key, this.loadChanges, this.setUndone, this.openConversation, this.openTasks});

  final ReviewChangesLoader? loadChanges;
  final ReviewChangeToggler? setUndone;

  /// Opens a source conversation; defaults to the conversation detail page.
  final void Function(BuildContext context, String conversationId)? openConversation;

  /// Opens the task list from a task change; defaults to the Tasks page.
  final void Function(BuildContext context)? openTasks;

  @override
  State<RecentChangesPage> createState() => _RecentChangesPageState();
}

class _RecentChangesPageState extends State<RecentChangesPage> {
  /// Ticks whenever [_changes] or [_busy] change, so an open sheet follows the page.
  final _revision = ValueNotifier<int>(0);
  List<ReviewChange> _changes = const [];
  Map<RecentChangeSection, List<RecentChangeGroup>> _groups = const {};
  String? _cursor;
  bool _loading = true;
  bool _failed = false;
  bool _loadingMore = false;
  final Set<String> _busy = {};

  ReviewChangesLoader get _load => widget.loadChanges ?? api.getReviewChanges;
  ReviewChangeToggler get _toggle => widget.setUndone ?? api.setReviewChangeUndone;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  @override
  void dispose() {
    _revision.dispose();
    super.dispose();
  }

  void _update(VoidCallback change) {
    setState(() {
      change();
      _groups = groupRecentChanges(_changes);
    });
    _revision.value++;
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    final result = await _load();
    if (!mounted) return;
    _update(() {
      _loading = false;
      switch (result) {
        case ApiSuccess(:final data):
          _changes = data.changes;
          _cursor = data.nextCursor;
        case ApiFailure():
          _failed = true;
      }
    });
  }

  Future<void> _more() async {
    final cursor = _cursor;
    if (cursor == null || _loadingMore) return;
    setState(() => _loadingMore = true);
    final result = await _load(cursor: cursor);
    if (!mounted) return;
    _update(() {
      _loadingMore = false;
      if (result case ApiSuccess(:final data)) {
        _changes = [..._changes, ...data.changes];
        _cursor = data.nextCursor;
      }
    });
  }

  /// Sets [undone] on each change in turn. There is no bulk endpoint; a failure leaves the rest
  /// applied and returns how many failed.
  Future<int> _setUndone(List<ReviewChange> changes, bool undone) async {
    var failures = 0;
    _update(() => _busy.addAll(changes.map((c) => c.changeId)));
    for (final change in changes) {
      final result = await _toggle(change.changeId, undone: undone);
      if (!mounted) return failures;
      _update(() {
        _busy.remove(change.changeId);
        if (result case ApiSuccess(:final data)) {
          _changes = [for (final c in _changes) c.changeId == data.changeId ? data : c];
        }
      });
      if (result is ApiFailure) failures++;
    }
    return failures;
  }

  Future<void> _toggleOne(ReviewChange change) async {
    final failed = context.l10n.reviewChangeFailed;
    final failures = await _setUndone([change], !change.undone);
    if (mounted && failures > 0) OmiFeedback.error(context, failed);
  }

  Future<void> _toggleGroup(RecentChangeGroup group) async {
    final l10n = context.l10n;
    final undo = !group.allUndone;
    final targets = undo ? group.active : group.changes;
    final failures = await _setUndone(targets, undo);
    if (!mounted || failures == 0) return;
    OmiFeedback.error(
      context,
      targets.length == 1 ? l10n.reviewChangeFailed : l10n.reviewChangesUndoPartial(failures, targets.length),
    );
  }

  RecentChangeGroup? _findGroup(String key) {
    for (final groups in _groups.values) {
      for (final group in groups) {
        if (group.key == key) return group;
      }
    }
    return null;
  }

  void _openConversation(BuildContext context, String conversationId) {
    final open = widget.openConversation;
    if (open != null) return open(context, conversationId);
    openChatBlockConversation(context, conversationId: conversationId);
  }

  void _openTasks(BuildContext context) {
    final open = widget.openTasks;
    if (open != null) return open(context);
    routeToPage(context, const ActionItemsPage());
  }

  void _openGroup(RecentChangeGroup group) {
    showOmiSheet<void>(
      context: context,
      title: _sectionLabel(context, group.section),
      builder: (sheetContext) => SingleChildScrollView(
        padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.md),
        child: RecentChangeSheetBody(
          key: const Key('recent_change_sheet'),
          listenable: _revision,
          group: () => _findGroup(group.key),
          isBusy: _busy.contains,
          onToggle: _toggleOne,
          onOpenConversation: (id) => _openConversation(sheetContext, id),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final Widget body;
    if (_loading) {
      body = const OmiLoadingState();
    } else if (_failed) {
      body = OmiErrorState(message: l10n.reviewChangesLoadFailed, onRetry: _refresh);
    } else if (_changes.isEmpty) {
      body = OmiEmptyState(icon: Icons.history, title: l10n.reviewNoChangesTitle, message: l10n.reviewNoChangesBody);
    } else {
      final rows = <Widget>[
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, 0, OmiSpacing.xxs, OmiSpacing.xs),
          child: Text(l10n.reviewChangesIntro, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        ),
      ];
      for (final MapEntry(key: section, value: groups) in _groups.entries) {
        rows.add(Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: ReviewSectionLabel(
              key: ValueKey('recent_changes_section_${section.name}'), label: _sectionLabel(context, section)),
        ));
        for (final group in groups) {
          rows.add(Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: RecentChangeRow(
              group: group,
              busy: group.changes.any((c) => _busy.contains(c.changeId)),
              onOpen: () => _openGroup(group),
              onToggleAll: () => _toggleGroup(group),
              onOpenTask: () => _openTasks(context),
            ),
          ));
        }
      }
      if (_cursor != null) {
        rows.add(Center(
          child: OmiButton.tertiary(label: l10n.reviewShowMore, isLoading: _loadingMore, onPressed: _more),
        ));
      }
      body = RefreshIndicator(
        onRefresh: _refresh,
        color: OmiColors.onAccent,
        backgroundColor: OmiColors.accent,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
          children: rows,
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.reviewRecentChanges)),
      body: body,
    );
  }
}

String _sectionLabel(BuildContext context, RecentChangeSection section) {
  final l10n = context.l10n;
  return switch (section) {
    RecentChangeSection.terms => l10n.reviewChangesSectionTerms,
    RecentChangeSection.memories => l10n.memories,
    RecentChangeSection.tasks => l10n.tasks,
    RecentChangeSection.titles => l10n.reviewChangesSectionTitles,
    RecentChangeSection.people => l10n.people,
    RecentChangeSection.conversations => l10n.conversations,
    RecentChangeSection.other => l10n.reviewChangesSectionOther,
  };
}

/// The glyph a change of [kind] wears wherever Omi's own changes are listed.
IconData reviewChangeIcon(ReviewChangeKind kind) => switch (kind) {
      ReviewChangeKind.rename => Icons.spellcheck,
      ReviewChangeKind.mergeMemories => Icons.call_merge,
      ReviewChangeKind.updatePerson => Icons.person_outline,
      ReviewChangeKind.labelSpeaker => Icons.record_voice_over_outlined,
      ReviewChangeKind.titleConversation => Icons.edit_outlined,
      ReviewChangeKind.closeTask => Icons.task_alt,
      ReviewChangeKind.other => Icons.auto_fix_high_outlined,
    };
