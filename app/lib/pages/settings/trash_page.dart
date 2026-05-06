import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

class TrashPage extends StatefulWidget {
  const TrashPage({super.key});

  @override
  State<TrashPage> createState() => _TrashPageState();
}

class _TrashPageState extends State<TrashPage> {
  bool _isLoading = true;
  List<ServerConversation> _conversations = [];

  @override
  void initState() {
    super.initState();
    _loadConversations();
  }

  Future<void> _loadConversations() async {
    final conversations = await getTrashedConversations();
    if (!mounted) return;
    setState(() {
      _conversations = conversations;
      _isLoading = false;
    });
  }

  int _daysRemaining(ServerConversation conversation) {
    final trashedAt = conversation.trashedAt;
    if (trashedAt == null) return 30;
    final elapsedDays = DateTime.now().difference(trashedAt).inDays.clamp(0, 30).toInt();
    return 30 - elapsedDays;
  }

  Future<void> _restore(ServerConversation conversation) async {
    final restored = await restoreConversationServer(conversation.id);
    if (!mounted || restored == null) return;
    setState(() {
      _conversations.removeWhere((item) => item.id == conversation.id);
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.restoreSuccess)));
  }

  Future<void> _deleteForever(ServerConversation conversation) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(context.l10n.deleteForeverConfirmTitle),
        content: Text(context.l10n.deleteConversationMessage),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: Text(context.l10n.cancel)),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(context.l10n.deleteForever, style: const TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    final deleted = await deleteConversationServer(conversation.id);
    if (!mounted || !deleted) return;
    setState(() {
      _conversations.removeWhere((item) => item.id == conversation.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white, title: Text(context.l10n.trash)),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _conversations.isEmpty
          ? _EmptyTrashState()
          : RefreshIndicator(
              onRefresh: _loadConversations,
              child: ListView.separated(
                padding: const EdgeInsets.all(16),
                itemBuilder: (context, index) => _TrashRow(
                  conversation: _conversations[index],
                  daysRemaining: _daysRemaining(_conversations[index]),
                  onRestore: () => _restore(_conversations[index]),
                  onDeleteForever: () => _deleteForever(_conversations[index]),
                ),
                separatorBuilder: (context, index) => const SizedBox(height: 10),
                itemCount: _conversations.length,
              ),
            ),
    );
  }
}

class _EmptyTrashState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.delete_outline, color: Color(0xFF8E8E93), size: 48),
            const SizedBox(height: 16),
            Text(
              context.l10n.trashEmpty,
              style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.trashDescription,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
            ),
          ],
        ),
      ),
    );
  }
}

class _TrashRow extends StatelessWidget {
  final ServerConversation conversation;
  final int daysRemaining;
  final VoidCallback onRestore;
  final VoidCallback onDeleteForever;

  const _TrashRow({
    required this.conversation,
    required this.daysRemaining,
    required this.onRestore,
    required this.onDeleteForever,
  });

  @override
  Widget build(BuildContext context) {
    final title = conversation.discarded
        ? conversation.getTranscript(maxCount: 100)
        : conversation.structured.title.decodeString;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(8)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title.isEmpty ? context.l10n.discardedConversation : title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.daysRemaining(daysRemaining),
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              TextButton.icon(
                onPressed: onRestore,
                icon: const Icon(Icons.restore, size: 18),
                label: Text(context.l10n.restoreConversation),
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: onDeleteForever,
                icon: const Icon(Icons.delete_forever, color: Colors.red, size: 18),
                label: Text(context.l10n.deleteForever, style: const TextStyle(color: Colors.red)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
