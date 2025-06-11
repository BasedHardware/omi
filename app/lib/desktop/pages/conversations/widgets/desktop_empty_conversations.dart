import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Premium minimal empty state for conversations - inspired by reference design
class DesktopEmptyConversations extends StatelessWidget {
  const DesktopEmptyConversations({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 480),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Clean minimal icon with better design
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                width: 1,
              ),
            ),
            child: const Icon(
              Icons.forum_rounded,
              color: ResponsiveHelper.textTertiary,
              size: 28,
            ),
          ),

          const SizedBox(height: 24),

          // Clean typography with better hierarchy
          const Text(
            'No conversations yet',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textPrimary,
              letterSpacing: -0.3,
            ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 8),

          const Text(
            'Start capturing conversations with your Omi device to see them here.',
            style: TextStyle(
              fontSize: 14,
              color: ResponsiveHelper.textTertiary,
              height: 1.4,
            ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 32),

          // Minimal getting started tips
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
        Container(
          width: 20,
          height: 20,
          decoration: BoxDecoration(
            color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Icon(
            icon,
            size: 12,
            color: ResponsiveHelper.purplePrimary,
          ),
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
