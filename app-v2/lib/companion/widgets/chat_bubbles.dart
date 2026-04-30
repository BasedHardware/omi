import 'package:flutter/material.dart';

import 'package:nooto_v2/companion/companion_turn.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class ChatBubbleAssistant extends StatefulWidget {
  final AssistantTextTurn turn;
  const ChatBubbleAssistant({super.key, required this.turn});

  @override
  State<ChatBubbleAssistant> createState() => _ChatBubbleAssistantState();
}

class _ChatBubbleAssistantState extends State<ChatBubbleAssistant> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _opacity;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 280))..forward();
    _opacity = CurvedAnimation(parent: _ctrl, curve: Curves.easeOut);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 340),
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.backgroundSecondary,
              borderRadius: BorderRadius.circular(AppStyles.radiusXLarge).copyWith(
                bottomLeft: const Radius.circular(6),
              ),
            ),
            child: Text(
              widget.turn.text,
              style: const TextStyle(fontSize: 15, height: 1.4, color: AppColors.textPrimary),
            ),
          ),
        ),
      ),
    );
  }
}

class ChatBubbleUser extends StatelessWidget {
  final UserTextTurn turn;
  const ChatBubbleUser({super.key, required this.turn});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 340),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.brandAccent,
            borderRadius: BorderRadius.circular(AppStyles.radiusXLarge).copyWith(
              bottomRight: const Radius.circular(6),
            ),
          ),
          child: Text(
            turn.text,
            style: const TextStyle(fontSize: 15, height: 1.4, color: Colors.white),
          ),
        ),
      ),
    );
  }
}
