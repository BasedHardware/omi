import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
}

typedef ConversationTaskCreator = Future<String?> Function(
  ActionItem item, {
  required bool completed,
  required String idempotencyKey,
});
typedef ConversationTaskUpdater = Future<bool> Function(String taskId, bool completed);
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
  /// references, not identities: one segment can carry several commitments, and the
  /// backend allows multiple identical items in a conversation, so the item's own
  /// description and due date disambiguate rows that share evidence.
  static String identity(ActionItem item) =>
      '${item.sourceSegmentIds.join('|')}|${item.description}|${item.dueAt?.millisecondsSinceEpoch ?? ''}';

  String? taskIdFor(ActionItem item) => item.targetTaskId ?? _taskIds[identity(item)];
  bool get pending => _pending.isNotEmpty;
  bool isPending(ActionItem item) => _pending.contains(identity(item));

  String idempotencyKeyFor(ActionItem item) => _key(identity(item));

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

  Future<bool> addToTasks(ActionItem item) async {
    await _restored;
    final identity = identityFor(item);
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

  Future<bool> setCompleted(ActionItem item, int itemIndex, bool completed) async {
    await _restored;
    final identity = identityFor(item);
    if (!_pending.add(identity)) return false;
    try {
      var taskId = taskIdFor(item);
      if (taskId == null && completed) {
        taskId = await createTask(item, completed: true, idempotencyKey: _key(identity));
        if (taskId == null) return false;
        _rememberTaskId(identity, taskId);
      } else if (taskId != null && !await updateTask(taskId, completed)) {
        return false;
      }
      return updateConversationItem(itemIndex, completed);
    } finally {
      _pending.remove(identity);
    }
  }

  String identityFor(ActionItem item) => identity(item);
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
  });

  final List<ActionItem> items;
  final String conversationId;
  final ValueChanged<List<String>> onShowInTranscript;

  @override
  State<ConversationActionItemsSection> createState() => _ConversationActionItemsSectionState();
}

class _ConversationActionItemsSectionState extends State<ConversationActionItemsSection> {
  final Set<String> _adding = {};
  final Set<String> _failed = {};

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
  );

  String _identity(ActionItem item) => ConversationActionItemTaskSession.identity(item);

  Future<void> _setCompleted(ActionItem item, int index, bool value) async {
    final identity = _identity(item);
    if (_taskSession.isPending(item)) return;
    setState(() => _adding.add(identity));
    final saved = await _taskSession.setCompleted(item, index, value);
    if (!mounted) return;
    setState(() => _adding.remove(identity));
    if (saved) {
      _failed.remove(identity);
      context.read<ConversationDetailProvider>().updateActionItemState(value, index);
    } else {
      setState(() => _failed.add(identity));
    }
  }

  Future<void> _addToTasks(ActionItem item) async {
    final identity = _identity(item);
    if (item.targetTaskId != null || _taskSession.taskIdFor(item) != null || _adding.contains(identity)) return;
    setState(() {
      _adding.add(identity);
      _failed.remove(identity);
    });
    final created = await _taskSession.addToTasks(item);
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

  Future<void> _openTask(ActionItem item) async {
    final taskId = _taskSession.taskIdFor(item);
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
                    _ActionItemRow(
                      key: Key('conversation-action-item-row-${_identity(active[i])}'),
                      item: active[i],
                      meta: ActionItemMeta.of(active[i], l10n: l10n, dates: dates),
                      adding: _adding.contains(_identity(active[i])) || _taskSession.isPending(active[i]),
                      failed: _failed.contains(_identity(active[i])),
                      linked: active[i].targetTaskId != null,
                      added: _taskSession.taskIdFor(active[i]) != null && active[i].targetTaskId == null,
                      onToggle: (value) => _setCompleted(active[i], indexed[i].$1, value),
                      onAddToTasks: () => _addToTasks(active[i]),
                      onOpenTask: () => _openTask(active[i]),
                      onShowInTranscript: () => widget.onShowInTranscript(active[i].sourceSegmentIds),
                    ),
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
                      Text(
                        item.description,
                        style: OmiType.callout.copyWith(
                          color: item.completed ? OmiColors.textSecondary : OmiColors.textPrimary,
                          decoration: item.completed ? TextDecoration.lineThrough : null,
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
                                  Flexible(child: Text(owner, style: secondary)),
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
                        Text(meta.context!, style: secondary),
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
