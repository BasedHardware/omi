import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/utils/l10n_extensions.dart';

class EmptyConversationsWidget extends StatelessWidget {
  final bool isStarredFilterActive;

  const EmptyConversationsWidget({super.key, this.isStarredFilterActive = false});

  @override
  Widget build(BuildContext context) {
    if (isStarredFilterActive) {
      return _buildStarredEmpty(context);
    }

    return _buildDefaultEmpty(context);
  }

  Widget _buildStarredEmpty(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: Colors.amber.withValues(alpha: 0.15),
                  width: 1.5,
                ),
                color: Colors.amber.withValues(alpha: 0.05),
              ),
              child: const Center(
                child: FaIcon(
                  FontAwesomeIcons.star,
                  color: Colors.amber,
                  size: 22,
                ),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              context.l10n.noStarredConversations,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w600,
                letterSpacing: -0.3,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.starConversationHint,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.4),
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }

  Widget _buildDefaultEmpty(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Icon container matching tasks style
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.08),
                  width: 1.5,
                ),
                color: Colors.white.withValues(alpha: 0.03),
              ),
              child: Icon(
                Icons.chat_bubble_outline_rounded,
                size: 26,
                color: Colors.white.withValues(alpha: 0.25),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              context.l10n.noConversationsYet,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w600,
                letterSpacing: -0.3,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.conversationsEmptyStateMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.4),
                fontSize: 14,
                height: 1.5,
              ),
            ),
            // Offset so content sits slightly above true center (accounts for nav bar)
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }
}
