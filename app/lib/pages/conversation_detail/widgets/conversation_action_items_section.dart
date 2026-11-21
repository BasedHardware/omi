import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/action_items.dart' show deleteActionItem;
import 'package:omi/backend/http/api/conversations.dart' show setConversationActionItemState;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What one action-item row says under its description. Every field is absent rather than
/// "Unknown": a row with no owner and no due date has no metadata line at all.
///
/// The same layout as the Mac (`ConversationActionItemRow`) and the web share page: the item,
/// then owner and due date on one line, then the context on its own line.
class ActionItemMeta {
  const ActionItemMeta({this.owner, this.due, this.dueAccessibility, this.context});

  /// "You" for the reader's own items, otherwise the name the extraction gave.
  final String? owner;
  final String? due;
  final String? dueAccessibility;
  final String? context;

  bool get hasOwnerOrDue => owner != null || due != null;

  static final _emailShaped = RegExp(r'[^\s@]+@[^\s@]+\.[^\s@]+');

  factory ActionItemMeta.of(ActionItem item, {required AppLocalizations l10n, required OmiDateFormat dates}) {
    final name = item.ownerName?.trim() ?? '';
    final owner = item.captureOwner == 'user' ? l10n.you : (name.isEmpty || _emailShaped.hasMatch(name) ? null : name);
    final dueAt = item.dueAt;
    final context = item.context?.trim() ?? '';
    return ActionItemMeta(
      owner: owner,
      due: dueAt == null
          ? null
          : item.dueCertainty == 'tentative'
              ? l10n.tentativeTaskDueDate(dates.dayHeader(dueAt.toLocal()))
              : l10n.taskDueDate(dates.dayHeader(dueAt.toLocal())),
      dueAccessibility: dueAt == null
          ? null
          : item.dueCertainty == 'tentative'
              ? l10n.tentativeTaskDueDateSemantics(dates.dayHeader(dueAt.toLocal()))
              : l10n.taskDueDate(dates.dayHeader(dueAt.toLocal())),
      context: context.isEmpty ? null : context,
    );
  }

  /// The row's text a Summary-tab search can match, in display order: the
  /// description, the owner's displayed name (never the localized "You" and
  /// never an email shape) and the context. Due labels are formatted per
  /// locale and stay out of both the count and the highlighting.
  static List<String> searchableTexts(ActionItem item) {
    final name = item.ownerName?.trim() ?? '';
    final ownerShown = item.captureOwner == 'user' || name.isEmpty || _emailShaped.hasMatch(name) ? null : name;
    final context = item.context?.trim() ?? '';
    return [
      item.description,
      if (ownerShown != null) ownerShown,
      if (context.isNotEmpty) context,
    ];
  }
}

/// The Summary tab's search result count includes the section's rows: the
/// page adds this to the note's own matches so `n/m` covers the action items
/// the tab renders. Deleted rows are not rendered and do not count.
int conversationActionItemSearchMatchCount(List<ActionItem> items, String query) {
  if (query.isEmpty) return 0;
  final pattern = RegExp(RegExp.escape(query), caseSensitive: false);
  var count = 0;
  for (final item in items) {
    if (item.deleted) continue;
    for (final text in ActionItemMeta.searchableTexts(item)) {
      count += pattern.allMatches(text).length;
    }
  }
  return count;
}

typedef ConversationTaskCreator = Future<String?> Function(
  ActionItem item, {
  required bool completed,
  required String idempotencyKey,
});
typedef ConversationTaskUpdater = Future<bool> Function(String taskId, bool completed);
typedef ConversationTaskDeleter = Future<bool> Function(String taskId);
typedef ConversationItemStateWriter = Future<bool> Function(int itemIndex, bool completed);

/// Owns task identity for one open conversation detail. The stable idempotency key protects a
/// retry after a lost create response, while the recorded task id makes later toggles update the
/// same task. Both survive page sessions: the key is derived from the conversation and the item's
/// content identity, and the task link is persisted, so navigating away or restarting can neither
/// unlink a promoted item nor mint a duplicate task.
class ConversationActionItemTaskSession {
  ConversationActionItemTaskSession({
    required this.conversationId,
    required this.createTask,
    required this.updateTask,
    required this.updateConversationItem,
    this.deleteTask,
    String Function()? newIdempotencyKey,
    Future<Map<String, String>> Function()? readPersistedTaskIds,
    Future<void> Function(Map<String, String>)? writePersistedTaskIds,
  })  : _newIdempotencyKey = newIdempotencyKey,
        _readPersistedTaskIds = readPersistedTaskIds ?? (() => _readStoredTaskIds(_storageKey(conversationId))),
        _writePersistedTaskIds =
            writePersistedTaskIds ?? ((taskIds) => _writeStoredTaskIds(_storageKey(conversationId), taskIds));

  static const _storagePrefix = 'omi.conversation_action_item_tasks';

  /// Conversations whose links stay on disk; the oldest fall off the end. Entries
  /// are tiny, but the store must not grow without bound.
  static const _storedConversationLimit = 50;
  static const _storageIndexKey = '$_storagePrefix.index';

  static String _storageKey(String conversationId) => '$_storagePrefix.$conversationId';

  static Map<String, String> _decodeTaskIds(String? raw) {
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return decoded.map((key, value) => MapEntry(key, value is String ? value : ''));
      }
    } catch (_) {}
    return {};
  }

  static Future<Map<String, String>> _readStoredTaskIds(String storageKey) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return _decodeTaskIds(prefs.getString(storageKey));
    } catch (_) {
      return {};
    }
  }

  static Future<void> _writeStoredTaskIds(String storageKey, Map<String, String> taskIds) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(storageKey, jsonEncode(taskIds));
      final index = prefs.getStringList(_storageIndexKey) ?? const [];
      final updated = [storageKey, ...index.where((key) => key != storageKey)];
      if (updated.length > _storedConversationLimit) {
        for (final evicted in updated.sublist(_storedConversationLimit)) {
          await prefs.remove(evicted);
        }
      }
      await prefs.setStringList(_storageIndexKey, updated.sublist(0, _storedConversationLimit));
    } catch (_) {}
  }

  final String conversationId;
  final ConversationTaskCreator createTask;
  final ConversationTaskUpdater updateTask;
  final ConversationItemStateWriter updateConversationItem;
  final ConversationTaskDeleter? deleteTask;
  final String Function()? _newIdempotencyKey;
  final Future<Map<String, String>> Function() _readPersistedTaskIds;
  final Future<void> Function(Map<String, String>) _writePersistedTaskIds;
  final Map<String, String> _taskIds = {};
  final Map<String, String> _idempotencyKeys = {};
  final Set<String> _pending = {};

  /// Completes when persisted links are loaded. Mutating methods await it so the
  /// first action on a fresh page session addresses a restored task instead of
  /// racing the read and minting a duplicate.
  late final Future<void> _restored = _readPersistedTaskIds().then((persisted) {
    persisted.forEach((identity, taskId) {
      _taskIds.putIfAbsent(identity, () => taskId);
    });
  });

  /// Content-stable identity for one extracted row. Segment IDs are evidence
  /// references, not identities: one segment can carry several commitments, and
  /// the backend allows multiple identical items in a conversation, so the item's
  /// own description and due date disambiguate rows that share evidence. The
  /// row's position disambiguates remaining twins: two rows with equal
  /// description, due date and evidence are two commitments, not one.
  static String identity(ActionItem item, {int? row}) =>
      '${row ?? ''}|${item.sourceSegmentIds.join('|')}|${item.description}|${item.dueAt?.millisecondsSinceEpoch ?? ''}';

  String? taskIdFor(ActionItem item, {int? row}) => item.targetTaskId ?? _taskIds[identity(item, row: row)];
  bool get pending => _pending.isNotEmpty;
  bool isPending(ActionItem item, {int? row}) => _pending.contains(identity(item, row: row));

  String idempotencyKeyFor(ActionItem item, {int? row}) => _key(identity(item, row: row));

  String _key(String identity) => _idempotencyKeys.putIfAbsent(
      identity,
      () =>
          _newIdempotencyKey?.call() ??
          'conversation-action-item:${_stableKeyPart(conversationId)}:${_stableKeyPart(identity)}');

  /// A retry — including one from a fresh page session — must recreate the same
  /// item's task, so the production key is derived from the conversation and item
  /// identity, never random. The backend returns the task an equal key already
  /// created, which is what keeps a re-opened page from minting a second task.
  static String _stableKeyPart(String value) => md5.convert(utf8.encode(value)).toString().substring(0, 16);

  void _rememberTaskId(String identity, String taskId) {
    _taskIds[identity] = taskId;
    _writePersistedTaskIds(Map<String, String>.of(_taskIds));
  }

  Future<bool> addToTasks(ActionItem item, {int? row}) async {
    await _restored;
    final identity = identityFor(item, row: row);
    if (item.targetTaskId != null || _taskIds.containsKey(identity)) return true;
    if (!_pending.add(identity)) return false;
    try {
      final taskId = await createTask(item, completed: false, idempotencyKey: _key(identity));
      if (taskId == null) return false;
      _rememberTaskId(identity, taskId);
      return true;
    } finally {
      _pending.remove(identity);
    }
  }

  /// Sets one row's completion and returns the conversation row index that was
  /// patched, or null on failure. The row's position is re-resolved against
  /// [currentRows] just before the conversation PATCH, so a reprocessed note
  /// cannot redirect the write onto a different extracted row; when the row is
  /// gone, nothing is mutated and the call reports failure.
  Future<int?> setCompleted(ActionItem item, int itemIndex, bool completed,
      {int? row, List<ActionItem>? currentRows}) async {
    await _restored;
    final identity = identityFor(item, row: row);
    if (!_pending.add(identity)) return null;
    String? createdTaskId;
    try {
      var taskId = taskIdFor(item, row: row);
      if (taskId == null && completed) {
        taskId = await createTask(item, completed: true, idempotencyKey: _key(identity));
        if (taskId == null) return null;
        createdTaskId = taskId;
        _rememberTaskId(identity, taskId);
      } else if (taskId != null && !await updateTask(taskId, completed)) {
        return null;
      }
      var index = itemIndex;
      if (currentRows != null) {
        final resolved = _resolveRow(item, row: row, rows: currentRows);
        if (resolved == null) return null;
        index = resolved;
      }
      final saved = await updateConversationItem(index, completed);
      if (!saved) {
        // The task mutation took effect but the note did not absorb it. Undo the
        // task side so Tasks and the summary cannot disagree across refreshes:
        // a task minted by this call is removed; an existing task is restored.
        if (createdTaskId != null) {
          if (deleteTask != null) {
            await deleteTask!(createdTaskId);
          }
          _taskIds.remove(identity);
          _writePersistedTaskIds(Map<String, String>.of(_taskIds));
        } else if (taskId != null) {
          await updateTask(taskId, !completed);
        }
        return null;
      }
      return index;
    } finally {
      _pending.remove(identity);
    }
  }

  /// Finds the row's current position in [rows]: the recorded index when the
  /// row still holds the same item, otherwise the unique row matching this
  /// item's identity. Null when the note no longer contains the row.
  int? _resolveRow(ActionItem item, {int? row, required List<ActionItem> rows}) {
    bool sameRow(ActionItem candidate) =>
        candidate.description == item.description &&
        candidate.dueAt == item.dueAt &&
        candidate.targetTaskId == item.targetTaskId;
    if (row != null && row < rows.length && sameRow(rows[row])) return row;
    final matches = rows.where(sameRow).toList();
    return matches.length == 1 ? rows.indexOf(matches.single) : null;
  }

  String identityFor(ActionItem item, {int? row}) => identity(item, row: row);
}

/// The note's action items, after its sections: the mobile twin of the Mac's Action Items card.
/// Read-only here; promoting an item or ticking it off happens in Tasks. Absent when the note has
/// none.
class ConversationActionItemsSection extends StatefulWidget {
  const ConversationActionItemsSection({
    super.key,
    required this.items,
    required this.conversationId,
    required this.onShowInTranscript,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.searchResultOffset = 0,
  });

  final List<ActionItem> items;
  final String conversationId;
  final ValueChanged<List<String>> onShowInTranscript;

  /// The Summary tab's active search, when one is running. Rows highlight
  /// their matches and scroll to the tab's current result.
  final String searchQuery;

  /// The tab's current search result (0-based) among ALL Summary-tab matches,
  /// or -1 when the section owns none of them.
  final int currentResultIndex;

  /// How many of the tab's Summary matches precede this section's first row;
  /// the page computes it alongside the total.
  final int searchResultOffset;

  @override
  State<ConversationActionItemsSection> createState() => _ConversationActionItemsSectionState();
}

class _ConversationActionItemsSectionState extends State<ConversationActionItemsSection> {
  final Set<String> _adding = {};
  final Set<String> _failed = {};

  /// One scroll anchor per rendered row while a search runs, so the tab's
  /// current result can be scrolled to like the note's own paragraphs.
  final Map<String, GlobalKey> _rowKeys = {};
  String? _owningRowIdentity;

  void _scrollToCurrentSearchResult() {
    final identity = _owningRowIdentity;
    if (identity == null) return;
    final context = _rowKeys[identity]?.currentContext;
    if (context != null) {
      Scrollable.ensureVisible(context, duration: const Duration(milliseconds: 250), alignment: 0.4);
    }
  }

  late final ConversationActionItemTaskSession _taskSession = ConversationActionItemTaskSession(
    conversationId: widget.conversationId,
    createTask: (item, {required completed, required idempotencyKey}) async =>
        (await context.read<ActionItemsProvider>().createActionItem(
                  description: item.description,
                  dueAt: item.dueAt,
                  conversationId: widget.conversationId,
                  completed: completed,
                  idempotencyKey: idempotencyKey,
                ))
            ?.id,
    updateTask: (id, value) => context.read<ActionItemsProvider>().updateActionItemStateById(id, value),
    updateConversationItem: (index, value) async =>
        setConversationActionItemState(widget.conversationId, [index], [value]),
    deleteTask: (id) => deleteActionItem(id),
  );

  String _identity(ActionItem item, int row) => ConversationActionItemTaskSession.identity(item, row: row);

  Future<void> _setCompleted(ActionItem item, int index, bool value) async {
    final identity = _identity(item, index);
    if (_taskSession.isPending(item, row: index)) return;
    setState(() => _adding.add(identity));
    final patchedIndex = await _taskSession.setCompleted(
      item,
      index,
      value,
      row: index,
      currentRows: context.read<ConversationDetailProvider>().conversationOrNull?.structured.actionItems,
    );
    if (!mounted) return;
    setState(() => _adding.remove(identity));
    if (patchedIndex != null) {
      _failed.remove(identity);
      context.read<ConversationDetailProvider>().updateActionItemState(value, patchedIndex);
    } else {
      setState(() => _failed.add(identity));
    }
  }

  Future<void> _addToTasks(ActionItem item, int index) async {
    final identity = _identity(item, index);
    if (item.targetTaskId != null || _taskSession.taskIdFor(item, row: index) != null || _adding.contains(identity)) {
      return;
    }
    setState(() {
      _adding.add(identity);
      _failed.remove(identity);
    });
    final created = await _taskSession.addToTasks(item, row: index);
    if (!mounted) return;
    setState(() {
      _adding.remove(identity);
      if (!created) {
        _failed.add(identity);
      } else {
        _failed.remove(identity);
      }
    });
  }

  Future<void> _openTask(ActionItem item, int index) async {
    final taskId = _taskSession.taskIdFor(item, row: index);
    if (taskId == null) return;
    final task = await context.read<ActionItemsProvider>().getActionItemById(taskId);
    if (task != null && mounted) showActionItemFormSheet(context, actionItem: task);
  }

  @override
  Widget build(BuildContext context) {
    final indexed = widget.items.indexed.where((entry) => !entry.$2.deleted).toList();
    final active = indexed.map((entry) => entry.$2).toList();
    if (active.isEmpty) return const SliverToBoxAdapter(child: SizedBox.shrink());
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    // Resolve which row (if any) owns the tab's current search result, and
    // which of that row's own matches is the current one. Rows are visited in
    // display order, so the arithmetic mirrors the page's count.
    String? owningRow;
    int owningRowLocalMatch = -1;
    if (widget.searchQuery.isNotEmpty && widget.currentResultIndex >= widget.searchResultOffset) {
      final pattern = RegExp(RegExp.escape(widget.searchQuery), caseSensitive: false);
      var consumed = widget.searchResultOffset;
      for (var i = 0; i < active.length; i++) {
        var rowMatches = 0;
        for (final text in ActionItemMeta.searchableTexts(active[i])) {
          rowMatches += pattern.allMatches(text).length;
        }
        if (widget.currentResultIndex < consumed + rowMatches) {
          owningRow = _identity(active[i], indexed[i].$1);
          owningRowLocalMatch = widget.currentResultIndex - consumed;
          break;
        }
        consumed += rowMatches;
      }
    }
    if (owningRow != _owningRowIdentity) {
      // The current result moved to another row: remember it before the frame
      // paints, then scroll it into view once its anchor exists.
      _owningRowIdentity = owningRow;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _scrollToCurrentSearchResult();
      });
    }
    return SliverToBoxAdapter(
      child: Padding(
        key: const ValueKey('conversation_action_items_section'),
        padding: const EdgeInsets.only(top: OmiSpacing.md, bottom: OmiSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Row(
                children: [
                  ExcludeSemantics(
                    child: Icon(Icons.checklist_rounded, size: 18, color: OmiColors.textSecondary),
                  ),
                  const SizedBox(width: OmiSpacing.xs),
                  Flexible(
                    child: Text(
                      l10n.meetingActionItemsTitle,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
            DecoratedBox(
              decoration: BoxDecoration(
                border: Border.all(color: OmiColors.border),
                borderRadius: OmiRadius.lgAll,
              ),
              child: Column(
                children: [
                  for (var i = 0; i < active.length; i++) ...[
                    if (i > 0) Divider(height: 1, thickness: 1, color: OmiColors.border),
                    Builder(builder: (context) {
                      final identity = _identity(active[i], indexed[i].$1);
                      // Only the row owning the current result needs a scroll
                      // anchor; the key is created in this build and read in
                      // the post-frame scroll callback.
                      final anchor = owningRow == identity ? _rowKeys.putIfAbsent(identity, () => GlobalKey()) : null;
                      return _ActionItemRow(
                        key: Key('conversation-action-item-row-$identity'),
                        rowAnchorKey: anchor,
                        item: active[i],
                        meta: ActionItemMeta.of(active[i], l10n: l10n, dates: dates),
                        adding: _adding.contains(identity) || _taskSession.isPending(active[i], row: indexed[i].$1),
                        failed: _failed.contains(identity),
                        linked: active[i].targetTaskId != null,
                        added: _taskSession.taskIdFor(active[i], row: indexed[i].$1) != null &&
                            active[i].targetTaskId == null,
                        highlightQuery: widget.searchQuery,
                        currentMatchInRow: owningRow == identity ? owningRowLocalMatch : -1,
                        onToggle: (value) => _setCompleted(active[i], indexed[i].$1, value),
                        onAddToTasks: () => _addToTasks(active[i], indexed[i].$1),
                        onOpenTask: () => _openTask(active[i], indexed[i].$1),
                        onShowInTranscript: () => widget.onShowInTranscript(active[i].sourceSegmentIds),
                      );
                    }),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionItemRow extends StatelessWidget {
  const _ActionItemRow({
    super.key,
    required this.item,
    required this.meta,
    required this.adding,
    required this.failed,
    required this.linked,
    required this.added,
    required this.onToggle,
    required this.onAddToTasks,
    required this.onOpenTask,
    required this.onShowInTranscript,
    this.rowAnchorKey,
    this.highlightQuery = '',
    this.currentMatchInRow = -1,
  });

  final ActionItem item;
  final ActionItemMeta meta;
  final bool adding;
  final bool failed;
  final bool linked;
  final bool added;
  final ValueChanged<bool> onToggle;
  final VoidCallback onAddToTasks;
  final VoidCallback onOpenTask;
  final VoidCallback onShowInTranscript;

  /// Scroll anchor for the Summary tab's search navigation; null unless a
  /// search is running or this row owns the current result.
  final Key? rowAnchorKey;

  /// Active Summary-tab search; non-empty rows highlight their matches.
  final String highlightQuery;

  /// Which of this row's own matches is the tab's current one, or -1.
  final int currentMatchInRow;

  /// Splits [text] into spans around case-insensitive query matches,
  /// highlighting them like the note's own search results. [searchIndex] is
  /// this text's position among the row's searchable texts (description,
  /// owner, context — in display order); -1 renders plain because the text is
  /// a localized label the tab's count does not include (e.g. "You").
  List<InlineSpan> _highlightedSpans(String text, TextStyle style, {required int searchIndex}) {
    if (highlightQuery.isEmpty || searchIndex < 0) return [TextSpan(text: text, style: style)];
    final pattern = RegExp(RegExp.escape(highlightQuery), caseSensitive: false);
    final searchable = ActionItemMeta.searchableTexts(item);
    var matchBase = 0;
    for (var i = 0; i < searchIndex && i < searchable.length; i++) {
      matchBase += pattern.allMatches(searchable[i]).length;
    }
    final matches = pattern.allMatches(text).toList();
    if (matches.isEmpty) return [TextSpan(text: text, style: style)];
    final spans = <InlineSpan>[];
    var previous = 0;
    for (var i = 0; i < matches.length; i++) {
      final match = matches[i];
      if (match.start > previous) spans.add(TextSpan(text: text.substring(previous, match.start), style: style));
      spans.add(TextSpan(
        text: text.substring(match.start, match.end),
        style: style.copyWith(
          backgroundColor: matchBase + i == currentMatchInRow ? OmiColors.warning : OmiColors.textTertiary,
          color: OmiColors.textPrimary,
        ),
      ));
      previous = match.end;
    }
    if (previous < text.length) spans.add(TextSpan(text: text.substring(previous), style: style));
    return spans;
  }

  /// The owner's search position: 1 when the row shows the extraction's own
  /// verbatim name, -1 for the reader's localized "You" label (not counted).
  int get _ownerSearchIndex => item.captureOwner == 'user' || meta.owner == null ? -1 : 1;

  /// The context's search position: after the owner when the name is counted.
  int get _contextSearchIndex => meta.context == null ? -1 : (_ownerSearchIndex < 0 ? 1 : 2);

  @override
  Widget build(BuildContext context) {
    final secondary = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    final owner = meta.owner;
    final due = meta.due;
    return GestureDetector(
      key: Key('conversation-action-item-gestures-${item.description.hashCode}'),
      onLongPress: () => _showMenu(context),
      child: Semantics(
        key: Key('conversation-action-item-semantics-${item.description.hashCode}'),
        label: item.description,
        value: item.completed ? context.l10n.completedStatus : context.l10n.notCompletedStatus,
        onTap: () => onToggle(!item.completed),
        onLongPress: () => _showMenu(context),
        child: MergeSemantics(
          child: Padding(
            key: rowAnchorKey,
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                IconButton(
                  key: Key('conversation-action-item-toggle-${item.description.hashCode}'),
                  tooltip: item.completed ? context.l10n.reopenTask : context.l10n.completeTask,
                  onPressed: () => onToggle(!item.completed),
                  icon: Icon(item.completed ? Icons.check_circle : Icons.radio_button_unchecked),
                  color: item.completed ? OmiColors.success : OmiColors.textTertiary,
                  constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                  padding: EdgeInsets.zero,
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text.rich(
                        TextSpan(
                          children: _highlightedSpans(
                              item.description,
                              OmiType.callout.copyWith(
                                color: item.completed ? OmiColors.textSecondary : OmiColors.textPrimary,
                                decoration: item.completed ? TextDecoration.lineThrough : null,
                              ),
                              searchIndex: 0),
                        ),
                      ),
                      if (meta.hasOwnerOrDue) ...[
                        const SizedBox(height: OmiSpacing.xxs),
                        Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: OmiSpacing.xs,
                          runSpacing: OmiSpacing.xxs,
                          children: [
                            if (owner != null)
                              Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  _OwnerInitials(name: owner),
                                  const SizedBox(width: OmiSpacing.xxs + 2),
                                  Flexible(
                                    child: Text.rich(
                                      TextSpan(
                                        children: _highlightedSpans(owner, secondary, searchIndex: _ownerSearchIndex),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            if (owner != null && due != null)
                              ExcludeSemantics(
                                  child:
                                      Text('·', style: secondary)), // omi-ux-allow: hardcoded-text -- separator glyph
                            if (due != null)
                              Semantics(
                                label: meta.dueAccessibility,
                                excludeSemantics: true,
                                child: Text(due, style: secondary),
                              ),
                          ],
                        ),
                      ],
                      if (meta.context != null) ...[
                        const SizedBox(height: OmiSpacing.xxs),
                        Text.rich(
                          TextSpan(
                            children: _highlightedSpans(meta.context!, secondary, searchIndex: _contextSearchIndex),
                          ),
                        ),
                      ],
                      if (adding || failed || linked || added) ...[
                        const SizedBox(height: OmiSpacing.xxs),
                        Text(
                          adding
                              ? context.l10n.addingToTasks
                              : failed
                                  ? context.l10n.tryAgain
                                  : linked
                                      ? context.l10n.openTask
                                      : context.l10n.taskAddedToTasks,
                          key: Key('conversation-action-item-task-state-${item.description.hashCode}'),
                          style: secondary,
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showMenu(BuildContext context) => showOmiRowMenu(
        context,
        title: item.description,
        actions: [
          if (!linked && !adding && !added)
            OmiMenuAction(
              key: Key('conversation-action-item-add-task-${item.description.hashCode}'),
              icon: Icons.add_task,
              label: failed ? context.l10n.tryAgain : context.l10n.addToTasks,
              onSelected: onAddToTasks,
            ),
          if (linked || added)
            OmiMenuAction(
              key: Key('conversation-action-item-open-task-${item.description.hashCode}'),
              icon: Icons.open_in_new,
              label: context.l10n.openTask,
              onSelected: onOpenTask,
            ),
          OmiMenuAction(
              key: Key('conversation-action-item-transcript-${item.description.hashCode}'),
              icon: Icons.subtitles_outlined,
              label: context.l10n.showInTranscript,
              onSelected: onShowInTranscript),
        ],
      );
}

/// A small initials disc, coloured like the person's avatar elsewhere.
class _OwnerInitials extends StatelessWidget {
  const _OwnerInitials({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: 18,
        height: 18,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: PersonAvatar.colorFor(name), shape: BoxShape.circle),
        // Speaker colours are dark in both appearances, so the initials are always light.
        child: Text(
          PersonAvatar.initials(name),
          style: OmiType.caption.copyWith(
              fontSize: 8, // omi-ux-allow: font-size-literal -- fixed 18 pt disc
              fontWeight: FontWeight.w600,
              color: OmiPalette.dark.textPrimary),
          maxLines: 1,
          textScaler: TextScaler.noScaling,
        ),
      ),
    );
  }
}
