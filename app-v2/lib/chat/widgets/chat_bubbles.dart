import 'package:flutter/material.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Per-message bubble. Dispatches to user vs assistant treatment based on
/// `message.role`. Keeps the chat-thread render loop a single Widget call.
class ChatBubble extends StatelessWidget {
  const ChatBubble({super.key, required this.message});
  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    return message.role == ChatRole.user
        ? _UserBubble(text: message.text)
        : _AssistantBubble(text: message.text, streaming: message.streaming);
  }
}

class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingXS),
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingL,
            vertical: AppStyles.spacingM,
          ),
          decoration: const BoxDecoration(
            color: AppColors.brandPrimary,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(AppStyles.radiusLarge),
              topRight: Radius.circular(AppStyles.radiusLarge),
              bottomLeft: Radius.circular(AppStyles.radiusLarge),
              bottomRight: Radius.circular(AppStyles.radiusSmall),
            ),
          ),
          child: Text(
            text,
            style: const TextStyle(
              fontSize: 16,
              color: AppColors.textPrimary,
              height: 1.4,
            ),
          ),
        ),
      ),
    );
  }
}

class _AssistantBubble extends StatelessWidget {
  const _AssistantBubble({required this.text, required this.streaming});
  final String text;
  final bool streaming;

  @override
  Widget build(BuildContext context) {
    final showCaret = streaming;
    final body = text.isEmpty && streaming ? '…' : text;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.85,
        ),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingXS),
          padding: const EdgeInsets.symmetric(
            horizontal: AppStyles.spacingL,
            vertical: AppStyles.spacingM,
          ),
          decoration: BoxDecoration(
            color: AppColors.backgroundSecondary,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(AppStyles.radiusLarge),
              topRight: Radius.circular(AppStyles.radiusLarge),
              bottomLeft: Radius.circular(AppStyles.radiusSmall),
              bottomRight: Radius.circular(AppStyles.radiusLarge),
            ),
            border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Flexible(
                child: Text(
                  body,
                  style: const TextStyle(
                    fontSize: 16,
                    color: AppColors.textSecondary,
                    height: 1.45,
                  ),
                ),
              ),
              if (showCaret) const _Caret(),
            ],
          ),
        ),
      ),
    );
  }
}

/// Blinking caret at end of streaming assistant text. 1Hz blink per the
/// design doc's motion language.
class _Caret extends StatefulWidget {
  const _Caret();

  @override
  State<_Caret> createState() => _CaretState();
}

class _CaretState extends State<_Caret>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1000),
  )..repeat();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, child) {
        final on = _ctrl.value < 0.5;
        return Padding(
          padding: const EdgeInsets.only(left: 2, bottom: 2),
          child: Opacity(
            opacity: on ? 1 : 0,
            child: Container(
              width: 2,
              height: 16,
              color: AppColors.brandPrimary,
            ),
          ),
        );
      },
    );
  }
}
