import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/chat/widgets/content_blocks/chat_block_chrome.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart' show conversationRowTitle;
import 'package:omi/pages/home/home_deep_links.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';

/// One row of an `/items` list once loaded: exactly one of [conversation], [task] or [memory] is
/// set, or none when the item is gone or not the reader's.
@immutable
class ItemListEntry {
  const ItemListEntry(this.ref, {this.conversation, this.task, this.memory});

  final ItemLinkRef ref;
  final ServerConversation? conversation;
  final ActionItemWithMetadata? task;
  final Memory? memory;

  bool get isAvailable => conversation != null || task != null || memory != null;
}

/// Loads the rows of an `/items` list. Each lookup returns null for an item that is gone or
/// belongs to someone else; the row then says so instead of failing the whole list.
class ItemListLoader {
  const ItemListLoader({this.conversationById, this.taskById, this.memoriesByIds});

  final Future<ServerConversation?> Function(String id)? conversationById;
  final Future<ActionItemWithMetadata?> Function(String id)? taskById;

  /// All memory ids of the list in one call: memories have no read-by-id endpoint, so they share
  /// one walk of the owner-wide index.
  final Future<Map<String, Memory>> Function(Set<String> ids)? memoriesByIds;

  /// One future per item, in list order. Rows resolve independently, so a slow memory walk does
  /// not hold back the conversations above it.
  List<Future<ItemListEntry>> load(List<ItemLinkRef> items) {
    // Read the signed-in owner only when a default lookup needs it (tests inject every lookup).
    String? owner;
    var ownerRead = false;
    String? uidAtOpen() {
      if (!ownerRead) {
        owner = FirebaseAuth.instance.currentUser?.uid;
        ownerRead = true;
      }
      return owner;
    }

    bool ownerIsCurrent() => uidAtOpen() != null && FirebaseAuth.instance.currentUser?.uid == uidAtOpen();

    final memoryIds = {
      for (final item in items)
        if (item.kind == 'memory') item.id
    };
    final memories = memoryIds.isEmpty
        ? Future.value(const <String, Memory>{})
        : (memoriesByIds?.call(memoryIds) ?? _defaultMemories(memoryIds, uidAtOpen(), ownerIsCurrent));

    return [
      for (final item in items)
        switch (item.kind) {
          'conversation' =>
            (conversationById?.call(item.id) ?? _defaultConversation(item.id, uidAtOpen(), ownerIsCurrent))
                .then((c) => ItemListEntry(item, conversation: c)),
          'task' => (taskById?.call(item.id) ?? _defaultTask(item.id, uidAtOpen(), ownerIsCurrent))
              .then((t) => ItemListEntry(item, task: t != null && itemListTaskIsOpenable(t) ? t : null)),
          'memory' => memories.then((found) => ItemListEntry(item, memory: found[item.id])),
          _ => Future.value(ItemListEntry(item)),
        }
            .catchError((Object _) => ItemListEntry(item)),
    ];
  }

  static Future<ServerConversation?> _defaultConversation(
      String id, String? uid, bool Function() ownerIsCurrent) async {
    if (uid == null) return null;
    final conversation = await getConversationById(id);
    return ownerIsCurrent() ? conversation : null;
  }

  static Future<ActionItemWithMetadata?> _defaultTask(String id, String? uid, bool Function() ownerIsCurrent) async {
    if (uid == null) return null;
    final result = await action_items_api.ActionItemsApi(baseUrl: Env.apiBaseUrl ?? '').getById(id);
    return ownerIsCurrent() && result is ApiSuccess<ActionItemWithMetadata> ? result.data : null;
  }

  static Future<Map<String, Memory>> _defaultMemories(
      Set<String> ids, String? uid, bool Function() ownerIsCurrent) async {
    if (uid == null) return const {};
    return resolveIndexedMemoriesByIds(ids, uid: uid, ownerIsCurrent: ownerIsCurrent);
  }
}

/// A task the list may open: live or completed, not paywalled, not replaced by another task.
/// Unlike Siri's index there is no 30-day cut-off for completed tasks: the link names the task.
bool itemListTaskIsOpenable(ActionItemWithMetadata task) =>
    task.id.isNotEmpty &&
    !task.isLocked &&
    (task.status == 'active' || task.status == 'completed') &&
    (task.supersededBy == null || task.supersededBy!.isEmpty);

/// Opens a loaded row through the page each kind already uses for a single item link.
typedef ItemListOpener = void Function(BuildContext context, ItemListEntry entry);

void openItemListEntry(BuildContext context, ItemListEntry entry) {
  final conversation = entry.conversation;
  final task = entry.task;
  final memory = entry.memory;
  if (conversation != null) {
    unawaited(routeToPage(context, ConversationDetailPage(conversation: conversation)));
  } else if (task != null) {
    unawaited(showActionItemFormSheet(context, actionItem: task));
  } else if (memory != null) {
    unawaited(showMemoryQuickEditSheet(context, memory, context.read<MemoriesProvider>(), readOnly: true));
  }
}

/// Shows the items of an `/items` link ("3 Items") over Home, in link order.
Future<void> showItemListSheet(
  BuildContext context,
  List<ItemLinkRef> items, {
  ItemListLoader loader = const ItemListLoader(),
  ItemListOpener onOpen = openItemListEntry,
}) {
  return showOmiSheet<void>(
    context: context,
    title: items.isEmpty ? null : context.l10n.itemLinkListTitle(items.length),
    builder: (_) => ItemListSheet(items: items, loader: loader, onOpen: onOpen),
  );
}

/// The body of the `/items` sheet: one card per item in the chat chip style for its kind, a
/// loading row until that item resolves, and a muted "No longer available" row for an item that is
/// gone or not the reader's.
class ItemListSheet extends StatefulWidget {
  const ItemListSheet({
    super.key,
    required this.items,
    this.loader = const ItemListLoader(),
    this.onOpen = openItemListEntry,
  });

  final List<ItemLinkRef> items;
  final ItemListLoader loader;
  final ItemListOpener onOpen;

  @override
  State<ItemListSheet> createState() => _ItemListSheetState();
}

class _ItemListSheetState extends State<ItemListSheet> {
  late List<Future<ItemListEntry>> _rows;

  @override
  void initState() {
    super.initState();
    _rows = widget.loader.load(widget.items);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.items.isEmpty) {
      return Padding(
        key: const Key('item-list-empty'),
        padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
        child: OmiEmptyState(icon: Icons.inbox_outlined, title: context.l10n.itemLinkListTitle(0)),
      );
    }
    return ListView.separated(
      key: const Key('item-list'),
      shrinkWrap: true,
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      itemCount: _rows.length,
      separatorBuilder: (_, __) => const SizedBox(height: OmiSpacing.xs),
      itemBuilder: (context, index) => FutureBuilder<ItemListEntry>(
        future: _rows[index],
        builder: (context, snapshot) => _ItemListRow(
          index: index,
          ref: widget.items[index],
          entry: snapshot.connectionState == ConnectionState.done ? snapshot.data : null,
          onOpen: widget.onOpen,
        ),
      ),
    );
  }
}

class _ItemListRow extends StatelessWidget {
  const _ItemListRow({required this.index, required this.ref, required this.entry, required this.onOpen});

  final int index;
  final ItemLinkRef ref;

  /// Null while loading.
  final ItemListEntry? entry;
  final ItemListOpener onOpen;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // The same icon and caption as the chat chips and edit receipts for each kind.
    final (IconData icon, String label) = switch (ref.kind) {
      'conversation' => (Icons.subject, l10n.chatBlockConversation),
      'task' => (Icons.checklist, l10n.chatBlockTask),
      _ => (Icons.psychology_outlined, l10n.chatBlockMemory),
    };
    final entry = this.entry;
    if (entry == null) {
      return ChatBlockLoading(key: Key('item-list-loading-$index'), icon: icon, label: label, message: l10n.loading);
    }
    final title = _title(context, entry);
    if (!entry.isAvailable || title == null) {
      return ChatBlockUnavailable(
        key: Key('item-list-unavailable-$index'),
        icon: icon,
        label: label,
        message: l10n.chatBlockUnavailable,
      );
    }
    final completed = entry.task?.completed ?? false;
    return ChatBlockCard(
      key: Key('item-list-row-$index'),
      semanticsLabel: '$label: $title',
      onTap: () => onOpen(context, entry),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: icon, label: label),
          const SizedBox(height: 4),
          Text(
            title,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: completed ? OmiColors.textSecondary : null,
                  decoration: completed ? TextDecoration.lineThrough : null,
                ),
          ),
        ],
      ),
    );
  }

  String? _title(BuildContext context, ItemListEntry entry) {
    final conversation = entry.conversation;
    if (conversation != null) return conversationRowTitle(context, conversation);
    final task = entry.task;
    if (task != null) return task.description.trim().isEmpty ? null : task.description.trim();
    final memory = entry.memory;
    if (memory != null) return memory.content.decodeString.trim().isEmpty ? null : memory.content.decodeString.trim();
    return null;
  }
}
