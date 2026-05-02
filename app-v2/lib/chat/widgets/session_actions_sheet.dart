import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_session.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Bottom sheet shown when the user long-presses a chat session row in the
/// drawer. Offers Pin/Unpin, Rename, and Delete actions.
///
/// Visual grammar:
///   ┌─────────────────────────────────────┐
///   │              ────                    │  ← drag handle
///   │  📌  Pin chat / Unpin chat           │
///   │  ✎   Rename chat                     │
///   │  🗑   Delete chat                    │
///   └─────────────────────────────────────┘
///
/// Tapping any action dismisses the sheet, then opens the corresponding
/// follow-up dialog (rename, delete-confirm) or fires the provider call
/// directly (pin toggle).
Future<void> showSessionActionsSheet(BuildContext context, ChatSession session) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: AppColors.backgroundTertiary,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(
        top: Radius.circular(AppStyles.radiusXLarge),
      ),
    ),
    useSafeArea: true,
    isScrollControlled: false,
    builder: (sheetContext) => _SessionActionsSheet(session: session),
  );
}

class _SessionActionsSheet extends StatelessWidget {
  const _SessionActionsSheet({required this.session});

  final ChatSession session;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(
          child: Container(
            width: 36,
            height: 4,
            margin: const EdgeInsets.only(top: 8, bottom: AppStyles.spacingM),
            decoration: BoxDecoration(
              color: AppColors.textTertiary.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        ),
        _ActionRow(
          icon: Icons.push_pin_rounded,
          label: session.pinned ? 'Unpin chat' : 'Pin chat',
          onTap: () {
            context.read<ChatProvider>().togglePin(session.id);
            Navigator.pop(context);
          },
        ),
        _ActionRow(
          icon: Icons.edit_outlined,
          label: 'Rename chat',
          onTap: () {
            Navigator.pop(context);
            _showRenameDialog(context, session);
          },
        ),
        _ActionRow(
          icon: Icons.delete_outline_rounded,
          label: 'Delete chat',
          onTap: () {
            Navigator.pop(context);
            _confirmAndDelete(context, session);
          },
        ),
        const SafeArea(top: false, child: SizedBox(height: AppStyles.spacingS)),
      ],
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 56),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingL,
            vertical: AppStyles.spacingM,
          ),
          child: Row(
            children: [
              Icon(icon, size: 18, color: AppColors.textPrimary),
              const SizedBox(width: AppStyles.spacingM),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 16,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Future<void> _showRenameDialog(BuildContext context, ChatSession session) async {
  final controller = TextEditingController(text: session.title);
  final provider = context.read<ChatProvider>();

  await showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: AppColors.backgroundSecondary,
      title: const Text(
        'Rename chat',
        style: TextStyle(color: AppColors.textPrimary),
      ),
      content: SizedBox(
        width: 320,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: controller,
              autofocus: true,
              style: const TextStyle(color: AppColors.textPrimary),
              decoration: const InputDecoration(
                hintText: 'Chat name',
                hintStyle: TextStyle(color: AppColors.textQuaternary),
                border: OutlineInputBorder(),
              ),
            ),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (ctx, value, _) {
                if (value.text.trim().isNotEmpty) {
                  return const SizedBox.shrink();
                }
                return const Padding(
                  padding: EdgeInsets.only(top: AppStyles.spacingS),
                  child: Text(
                    "Name can't be empty.",
                    style: TextStyle(
                      fontSize: 13,
                      color: AppColors.errorColor,
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext),
          child: const Text(
            'Cancel',
            style: TextStyle(color: AppColors.textTertiary),
          ),
        ),
        TextButton(
          onPressed: () async {
            final ok = await provider.renameSession(session.id, controller.text);
            if (ok && dialogContext.mounted) {
              Navigator.pop(dialogContext);
            }
          },
          child: const Text(
            'Save',
            style: TextStyle(color: AppColors.brandPrimary),
          ),
        ),
      ],
    ),
  );

  controller.dispose();
}

Future<void> _confirmAndDelete(BuildContext context, ChatSession session) async {
  final provider = context.read<ChatProvider>();
  final ok = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      backgroundColor: AppColors.backgroundSecondary,
      title: const Text(
        'Delete chat?',
        style: TextStyle(color: AppColors.textPrimary),
      ),
      content: const Text(
        'This conversation will be removed permanently.',
        style: TextStyle(color: AppColors.textTertiary),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: const Text(
            'Cancel',
            style: TextStyle(color: AppColors.textTertiary),
          ),
        ),
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, true),
          child: const Text(
            'Delete',
            style: TextStyle(color: AppColors.errorColor),
          ),
        ),
      ],
    ),
  );
  if (ok != true) return;
  await provider.deleteSession(session.id);
}
