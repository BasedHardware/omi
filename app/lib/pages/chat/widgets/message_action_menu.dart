import 'package:flutter/material.dart';

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
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(20),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 22.0, horizontal: 22.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey[900],
                borderRadius: BorderRadius.circular(12),
              ),
              child:
                  getMarkdownWidget(context, '${message.substring(0, message.length > 200 ? 200 : message.length)}...'),
            ),
            const SizedBox(height: 16),
            _buildActionButton(
              title: 'Copy',
              icon: Icons.copy,
              onTap: onCopy,
            ),
            _buildActionButton(
              title: 'Select Text',
              icon: Icons.description_outlined,
              onTap: onSelectText,
            ),
            _buildActionButton(
              title: 'Share',
              icon: Icons.share,
              onTap: onShare,
            ),
            if (onThumbsDown != null) ...[
              _buildActionButton(
                title: 'Not Helpful',
                icon: Icons.thumb_down_alt_outlined,
                onTap: onThumbsDown,
              ),
            ],
            _buildActionButton(
              title: 'Report',
              icon: Icons.report_gmailerrorred,
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
    required IconData icon,
    required Function()? onTap,
    bool isDestructive = false,
  }) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12.0),
        child: Row(
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: 16,
                color: isDestructive ? Colors.red : Colors.white,
              ),
            ),
            const Spacer(),
            Icon(
              icon,
              size: 20,
              color: isDestructive ? Colors.red : Colors.white,
            ),
          ],
        ),
      ),
    );
  }
}
