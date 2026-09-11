import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// App-detail actions; the page retains navigation and availability ownership.
class AppDetailAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String appName;
  final VoidCallback onBack;
  final VoidCallback? onChat;
  final VoidCallback? onOpen;
  final ValueChanged<BuildContext>? onShare;
  final VoidCallback? onEdit;
  final bool chatLoading;

  const AppDetailAppBar({
    super.key,
    required this.appName,
    required this.onBack,
    this.onChat,
    this.onOpen,
    this.onShare,
    this.onEdit,
    this.chatLoading = false,
  });

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  Widget _button({
    required String name,
    required String tooltip,
    required Widget icon,
    required VoidCallback? onPressed,
  }) =>
      SizedBox(
        width: 48,
        height: 48,
        child: IconButton(
          key: ValueKey('app_detail_$name'),
          padding: EdgeInsets.zero,
          tooltip: tooltip,
          onPressed: onPressed,
          icon: Container(
            width: 36,
            height: 36,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.3), shape: BoxShape.circle),
            child: icon,
          ),
        ),
      );

  @override
  Widget build(BuildContext context) => AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        automaticallyImplyLeading: false,
        leading: Center(
            child: _button(
          name: 'back',
          tooltip: context.l10n.back,
          icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16, color: Colors.white),
          onPressed: onBack,
        )),
        actions: [
          if (onChat != null)
            _button(
              name: 'chat',
              tooltip: context.l10n.chatWithAppName(appName.decodeString),
              onPressed: chatLoading ? null : onChat,
              icon: chatLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 1.5,
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    )
                  : const FaIcon(FontAwesomeIcons.solidComments, size: 16, color: Colors.white),
            ),
          if (onOpen != null)
            _button(
              name: 'open',
              tooltip: context.l10n.open,
              icon: const Icon(Icons.web, size: 20, color: Colors.white),
              onPressed: onOpen,
            ),
          if (onShare != null)
            Builder(
              builder: (buttonContext) => _button(
                name: 'share',
                tooltip: context.l10n.share,
                icon: const FaIcon(FontAwesomeIcons.arrowUpFromBracket, size: 16, color: Colors.white),
                onPressed: () => onShare!(buttonContext),
              ),
            ),
          if (onEdit != null)
            _button(
              name: 'edit',
              tooltip: context.l10n.edit,
              icon: const FaIcon(FontAwesomeIcons.edit, size: 16, color: Colors.white),
              onPressed: onEdit,
            ),
          const SizedBox(width: 8),
        ],
      );
}
