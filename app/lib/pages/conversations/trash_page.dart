import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class TrashPage extends StatefulWidget {
  const TrashPage({super.key});

  @override
  State<TrashPage> createState() => _TrashPageState();
}

class _TrashPageState extends State<TrashPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ConversationProvider>().fetchTrashedConversations();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: IconButton(
          icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          context.l10n.trash,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
        ),
        centerTitle: true,
        actions: [
          Consumer<ConversationProvider>(
            builder: (context, provider, child) {
              if (provider.trashedConversations.isEmpty) return const SizedBox.shrink();
              return TextButton(
                onPressed: () => _showEmptyTrashDialog(context, provider),
                child: Text(
                  context.l10n.emptyTrash,
                  style: TextStyle(color: Colors.redAccent.shade200, fontWeight: FontWeight.w500),
                ),
              );
            },
          ),
        ],
      ),
      body: Consumer<ConversationProvider>(
        builder: (context, provider, child) {
          if (provider.isLoadingTrash) {
            return const Center(child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white));
          }
          if (provider.trashedConversations.isEmpty) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FaIcon(FontAwesomeIcons.trash, color: Colors.grey.shade600, size: 48),
                  const SizedBox(height: 16),
                  Text(
                    context.l10n.trashIsEmpty,
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 18, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.deletedConversationsAppearHere,
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 14),
                  ),
                ],
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            itemCount: provider.trashedConversations.length,
            separatorBuilder: (_, __) => const Divider(height: 1, color: Color(0xFF3C3C43)),
            itemBuilder: (context, index) {
              final conversation = provider.trashedConversations[index];
              return _TrashItem(
                conversation: conversation,
                onRestore: () => provider.restoreConversationFromTrash(conversation.id),
                onPermanentDelete: () => _confirmPermanentDelete(context, provider, conversation),
              );
            },
          );
        },
      ),
    );
  }

  void _confirmPermanentDelete(BuildContext context, ConversationProvider provider, ServerConversation conversation) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        title: Text(context.l10n.deletePermanentlyTitle, style: const TextStyle(color: Colors.white)),
        content: Text(
          context.l10n.deletePermanentlyMessage,
          style: const TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              provider.permanentlyDeleteFromTrash(conversation.id);
            },
            child: Text(context.l10n.deletePermanently, style: TextStyle(color: Colors.redAccent.shade200)),
          ),
        ],
      ),
    );
  }

  void _showEmptyTrashDialog(BuildContext dialogContext, ConversationProvider provider) {
    showDialog(
      context: dialogContext,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        title: Text(context.l10n.emptyTrashTitle, style: const TextStyle(color: Colors.white)),
        content: Text(
          context.l10n.emptyTrashMessage,
          style: const TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              provider.emptyTrash();
            },
            child: Text(context.l10n.emptyTrash, style: TextStyle(color: Colors.redAccent.shade200)),
          ),
        ],
      ),
    );
  }
}

class _TrashItem extends StatelessWidget {
  final ServerConversation conversation;
  final VoidCallback onRestore;
  final VoidCallback onPermanentDelete;

  const _TrashItem({
    required this.conversation,
    required this.onRestore,
    required this.onPermanentDelete,
  });

  @override
  Widget build(BuildContext context) {
    final title = conversation.structured.title;
    final deletedAt = conversation.deletedAt;
    final deletedDate = deletedAt != null
        ? '${deletedAt.day}/${deletedAt.month}/${deletedAt.year}'
        : context.l10n.recently;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  context.l10n.deletedDate(deletedDate),
                  style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                ),
              ],
            ),
          ),
          IconButton(
            icon: const FaIcon(FontAwesomeIcons.rotateLeft, color: Colors.white, size: 14),
            tooltip: context.l10n.restore,
            onPressed: onRestore,
          ),
          const SizedBox(width: 4),
          IconButton(
            icon: FaIcon(FontAwesomeIcons.trashCan, color: Colors.redAccent.shade200, size: 14),
            tooltip: context.l10n.deletePermanentlyTooltip,
            onPressed: onPermanentDelete,
          ),
        ],
      ),
    );
  }
}
