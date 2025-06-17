import 'package:flutter/material.dart';
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopMessageActionMenu extends StatelessWidget {
  final Function()? onCopy;
  final Function()? onSelectText;
  final Function()? onShare;
  final Function()? onReport;
  final String message;

  const DesktopMessageActionMenu({
    super.key,
    this.onCopy,
    this.onSelectText,
    this.onShare,
    this.onReport,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(16),
        ),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary,
          width: 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 24.0, horizontal: 24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundQuaternary,
                  width: 1,
                ),
              ),
              child: getMarkdownWidget(
                context,
                '${message.substring(0, message.length > 200 ? 200 : message.length)}...',
              ),
            ),
            const SizedBox(height: 20),

            // Action buttons with desktop styling
            _buildActionButton(
              title: 'Copy',
              icon: Icons.copy_outlined,
              onTap: onCopy,
            ),
            const SizedBox(height: 4),
            _buildActionButton(
              title: 'Select Text',
              icon: Icons.text_fields_outlined,
              onTap: onSelectText,
            ),
            const SizedBox(height: 4),
            _buildActionButton(
              title: 'Share',
              icon: Icons.share_outlined,
              onTap: onShare,
            ),
            const SizedBox(height: 4),
            _buildActionButton(
              title: 'Report',
              icon: Icons.report_outlined,
              onTap: onReport,
              isDestructive: true,
            ),
            const SizedBox(height: 12),
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
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 12.0),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: Colors.transparent,
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Icon(
                icon,
                size: 18,
                color: isDestructive ? Colors.red.shade400 : ResponsiveHelper.textSecondary,
              ),
              const SizedBox(width: 12),
              Text(
                title,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                  color: isDestructive ? Colors.red.shade400 : ResponsiveHelper.textPrimary,
                ),
              ),
              const Spacer(),
              Icon(
                Icons.chevron_right,
                size: 16,
                color: isDestructive ? Colors.red.shade400.withOpacity(0.6) : ResponsiveHelper.textTertiary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
