import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Ask about this conversation" (v2): a 54 pt glass capsule floating over the bottom of a
/// conversation, the Omi mark leading. Opens Ask Omi scoped to the conversation.
class ConversationAskBar extends StatelessWidget {
  const ConversationAskBar({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = context.l10n.askAboutThisConversationPlaceholder;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      onTap: onTap,
      child: OmiPressable(
        key: const Key('conversation_ask_bar'),
        onTap: onTap,
        child: OmiGlass(
          borderRadius: OmiRadius.pillAll,
          child: SizedBox(
            height: 54,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: Row(
                children: [
                  const OmiRingLogo(size: 22),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
