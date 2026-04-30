import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/widgets/chat_bubbles.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Tab 1: chat with the assistant against `/v2/messages`. v0 is a single
/// global thread (multi-session lands later). The composer pill on Home
/// taps through here and we auto-focus when [autoFocus] is true so the
/// keyboard appears in the same gesture.
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, this.autoFocus = false});

  final bool autoFocus;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _input = TextEditingController();
  final _focus = FocusNode();
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    if (widget.autoFocus) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _focus.requestFocus();
      });
    }
    // Scroll to bottom whenever a new message lands.
    final provider = context.read<ChatProvider>();
    provider.addListener(_scrollToBottomSoon);
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
  }

  @override
  void dispose() {
    context.read<ChatProvider>().removeListener(_scrollToBottomSoon);
    _input.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToBottomSoon() {
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());
  }

  void _scrollToBottom() {
    if (!_scroll.hasClients) return;
    _scroll.animateTo(
      _scroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  Future<void> _submit() async {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    HapticFeedback.lightImpact();
    await context.read<ChatProvider>().send(text);
  }

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatProvider>();
    return Column(
      children: [
        Expanded(
          child: chat.isEmpty ? const _EmptyState() : _MessageList(scroll: _scroll, chat: chat),
        ),
        _Composer(
          controller: _input,
          focus: _focus,
          enabled: !chat.sending,
          onSubmit: _submit,
        ),
      ],
    );
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({required this.scroll, required this.chat});
  final ScrollController scroll;
  final ChatProvider chat;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      controller: scroll,
      padding: const EdgeInsets.symmetric(
        horizontal: AppStyles.spacingL,
        vertical: AppStyles.spacingM,
      ),
      itemCount: chat.messages.length,
      itemBuilder: (_, i) => ChatBubble(message: chat.messages[i]),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXL),
        child: Text(
          "Ask me about your day, what's pending, or anything you're "
          'trying to figure out.',
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 16,
            color: AppColors.textTertiary,
            height: 1.5,
          ),
        ),
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.focus,
    required this.enabled,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final FocusNode focus;
  final bool enabled;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final bottomSafe = MediaQuery.of(context).padding.bottom;
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.backgroundPrimary,
        border: Border(top: BorderSide(color: Colors.white10, width: 1)),
      ),
      padding: EdgeInsets.fromLTRB(
        AppStyles.spacingL,
        AppStyles.spacingM,
        AppStyles.spacingL,
        bottomSafe + AppStyles.spacingS,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.backgroundSecondary,
                borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
                border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
              ),
              padding: const EdgeInsets.symmetric(
                horizontal: AppStyles.spacingL,
                vertical: AppStyles.spacingS,
              ),
              child: TextField(
                controller: controller,
                focusNode: focus,
                enabled: enabled,
                minLines: 1,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                style: const TextStyle(
                  fontSize: 16,
                  color: AppColors.textPrimary,
                ),
                cursorColor: AppColors.brandPrimary,
                decoration: const InputDecoration(
                  hintText: 'Ask Nooto anything…',
                  hintStyle: TextStyle(
                    fontSize: 16,
                    color: AppColors.textTertiary,
                  ),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                ),
                onSubmitted: (_) => onSubmit(),
              ),
            ),
          ),
          const SizedBox(width: AppStyles.spacingS),
          _SendButton(enabled: enabled, onTap: onSubmit),
        ],
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({required this.enabled, required this.onTap});
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color =
        enabled ? AppColors.brandPrimary : AppColors.brandPrimary.withValues(alpha: 0.4);
    return Semantics(
      button: true,
      label: 'Send message',
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(AppStyles.touchTargetMinimum / 2),
        child: Container(
          width: AppStyles.touchTargetMinimum,
          height: AppStyles.touchTargetMinimum,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(AppStyles.touchTargetMinimum / 2),
          ),
          child: const Icon(
            Icons.arrow_upward_rounded,
            color: AppColors.textPrimary,
            size: 22,
          ),
        ),
      ),
    );
  }
}
