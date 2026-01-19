import 'package:flutter/material.dart';

import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopEmptyConversations extends StatelessWidget {
  const DesktopEmptyConversations({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 480),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          OmiEmptyState(
            icon: Icons.forum_rounded,
            title: context.l10n.noConversationsYet,
            message: context.l10n.startCapturingConversations,
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
                  context,
                  icon: Icons.phone_android_rounded,
                  text: context.l10n.useMobileAppToCapture,
                ),
                const SizedBox(height: 16),
                _buildTipItem(
                  context,
                  icon: Icons.auto_awesome_rounded,
                  text: context.l10n.conversationsProcessedAutomatically,
                ),
                const SizedBox(height: 16),
                _buildTipItem(
                  context,
                  icon: Icons.insights_rounded,
                  text: context.l10n.getInsightsInstantly,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTipItem(
    BuildContext context, {
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
