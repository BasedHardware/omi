import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'markdown_message_widget.dart';

class MessageActionMenu extends StatelessWidget {
  final Function()? onCopy;
  final Function()? onSelectText;
  final Function()? onShare;
  final Function()? onReport;
  final Function()? onThumbsUp;
  final Function()? onThumbsDown;
  final String message;

  const MessageActionMenu({
    super.key,
    this.onCopy,
    this.onSelectText,
    this.onShare,
    this.onReport,
    this.onThumbsUp,
    this.onThumbsDown,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 22.0, horizontal: 22.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: Colors.grey[900], borderRadius: BorderRadius.circular(12)),
              child: getMarkdownWidget(
                context,
                '${message.substring(0, message.length > 200 ? 200 : message.length)}...',
              ),
            ),
            const SizedBox(height: 16),
            _buildActionButton(title: context.l10n.copy, icon: const Icon(Icons.copy), onTap: onCopy),
            _buildActionButton(
              title: context.l10n.selectText,
              icon: const Icon(Icons.description_outlined),
              onTap: onSelectText,
            ),
            _buildActionButton(title: context.l10n.share, icon: const FaIcon(FontAwesomeIcons.share), onTap: onShare),
            if (onThumbsDown != null) ...[
              _buildActionButton(
                title: context.l10n.notHelpful,
                icon: const Icon(Icons.thumb_down_alt_outlined),
                onTap: onThumbsDown,
              ),
            ],
            _buildActionButton(
              title: context.l10n.report,
              icon: const Icon(Icons.report_gmailerrorred),
              onTap: onReport,
              isDestructive: true,
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButton({
    required String title,
    required Widget icon,
    required Function()? onTap,
    bool isDestructive = false,
  }) {
    final color = isDestructive ? Colors.red : Colors.white;
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12.0),
        child: Row(
          children: [
            Text(title, style: TextStyle(fontSize: 16, color: color)),
            const Spacer(),
            IconTheme(
              data: IconThemeData(color: color, size: 20),
              child: icon,
            ),
          ],
        ),
      ),
    );
  }
}
