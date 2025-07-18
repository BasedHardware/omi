import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';

class DesktopEmptyConversations extends StatelessWidget {
  const DesktopEmptyConversations({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 480),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const OmiEmptyState(
            icon: Icons.forum_rounded,
            title: 'No conversations yet',
            message: 'Start capturing conversations with your Omi device to see them here.',
            iconSize: 48,
            iconPadding: 24,
            color: ResponsiveHelper.purplePrimary,
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                width: 1,
              ),
            ),
            child: Column(
              children: [
                _buildTipItem(
                  icon: Icons.phone_android_rounded,
                  text: 'Use your mobile app to capture audio',
                ),
                const SizedBox(height: 16),
                _buildTipItem(
                  icon: Icons.auto_awesome_rounded,
                  text: 'Conversations are processed automatically',
                ),
                const SizedBox(height: 16),
                _buildTipItem(
                  icon: Icons.insights_rounded,
                  text: 'Get insights and summaries instantly',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTipItem({
    required IconData icon,
    required String text,
  }) {
    return Row(
      children: [
        OmiIconButton(
          icon: icon,
          style: OmiIconButtonStyle.filled,
          color: ResponsiveHelper.purplePrimary,
          size: 20,
          iconSize: 12,
          borderRadius: 4,
          onPressed: null,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w400,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}
