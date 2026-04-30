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
              bottomRight: Radius.circular(AppStyles.radiusMedium),
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
    final isTyping = text.isEmpty && streaming;
    final showCaret = streaming && !isTyping;

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
              bottomLeft: Radius.circular(AppStyles.radiusMedium),
              bottomRight: Radius.circular(AppStyles.radiusLarge),
            ),
            border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
          ),
          child: isTyping
              ? const _TypingDots()
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Flexible(
                      child: Text(
                        text,
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

/// Three dots that bounce in sequence (~1.2s cycle) while we wait for the
/// first streaming chunk. Mirrors the Messages typing indicator.
class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  double _dotOpacity(double t, double phase) {
    // Triangle wave centered on `phase` so each dot peaks ~400ms apart.
    final delta = (t - phase).abs();
    final wrapped = delta > 0.5 ? 1 - delta : delta;
    return 0.35 + (1 - (wrapped * 2).clamp(0.0, 1.0)) * 0.65;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 18,
      child: AnimatedBuilder(
        animation: _ctrl,
        builder: (_, child) {
          final t = _ctrl.value;
          return Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              _Dot(opacity: _dotOpacity(t, 0.0)),
              const SizedBox(width: 4),
              _Dot(opacity: _dotOpacity(t, 0.33)),
              const SizedBox(width: 4),
              _Dot(opacity: _dotOpacity(t, 0.66)),
            ],
          );
        },
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.opacity});
  final double opacity;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: opacity,
      child: Container(
        width: 6,
        height: 6,
        decoration: const BoxDecoration(
          color: AppColors.textTertiary,
          shape: BoxShape.circle,
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
