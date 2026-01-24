import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/utils/l10n_extensions.dart';

class EmptyConversationsWidget extends StatefulWidget {
  final bool isStarredFilterActive;

  const EmptyConversationsWidget({
    super.key,
    this.isStarredFilterActive = false,
  });

  @override
  State<EmptyConversationsWidget> createState() => _EmptyConversationsWidgetState();
}

class _EmptyConversationsWidgetState extends State<EmptyConversationsWidget> {
  @override
  Widget build(BuildContext context) {
    if (widget.isStarredFilterActive) {
      return Padding(
        padding: const EdgeInsets.only(top: 80.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.amber.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: const FaIcon(
                FontAwesomeIcons.star,
                color: Colors.amber,
                size: 32,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              context.l10n.noStarredConversations,
              style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32.0),
              child: Text(
                context.l10n.starConversationHint,
                style: const TextStyle(color: Colors.grey, fontSize: 14),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(top: 120.0),
      child: Text(
        context.l10n.noConversationsYet,
        style: const TextStyle(color: Colors.grey, fontSize: 16),
      ),
    );
  }
}
