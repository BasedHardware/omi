import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/chat/widgets/stop_streaming_button.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Per-message bubble. Dispatches to user vs assistant treatment based on
/// `message.role`. Keeps the chat-thread render loop a single Widget call.
class ChatBubble extends StatelessWidget {
  const ChatBubble({super.key, required this.message, this.onStopGenerating});
  final ChatMessage message;

  /// Tap handler for the "Stop generating" button rendered inside the
  /// streaming assistant bubble. Caller wires to `provider.stopActiveStream`.
  /// Null disables the button (bubble still renders the streaming caret).
  final VoidCallback? onStopGenerating;

  @override
  Widget build(BuildContext context) {
    return message.role == ChatRole.user
        ? _UserBubble(text: message.text)
        : _AssistantBubble(
            text: message.text,
            streaming: message.streaming,
            stopped: message.stopped,
            toolEvents: message.toolEvents,
            onStopGenerating: onStopGenerating,
          );
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
  const _AssistantBubble({
    required this.text,
    required this.streaming,
    required this.stopped,
    required this.toolEvents,
    this.onStopGenerating,
  });
  final String text;
  final bool streaming;
  final bool stopped;
  final List<String> toolEvents;
  final VoidCallback? onStopGenerating;

  @override
  Widget build(BuildContext context) {
    final isTyping = text.isEmpty && streaming && toolEvents.isEmpty;
    final hasTools = toolEvents.isNotEmpty;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.85,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
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
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (hasTools) ...[
                          for (final label in toolEvents)
                            _ToolEventChip(
                              label: label,
                              inProgress: streaming &&
                                  text.isEmpty &&
                                  label == toolEvents.last,
                            ),
                          if (text.isNotEmpty)
                            const SizedBox(height: AppStyles.spacingS),
                        ],
                        if (text.isNotEmpty)
                          MarkdownBody(
                            data: text,
                            selectable: true,
                            softLineBreak: true,
                            styleSheet: _markdownStyle(context),
                          )
                        else if (streaming)
                          // Tools running but no text yet — show typing dots.
                          const Padding(
                            padding: EdgeInsets.only(top: AppStyles.spacingXS),
                            child: _TypingDots(),
                          ),
                        if (stopped) const StoppedMarker(),
                      ],
                    ),
            ),
            // Stop button outside the bubble, left-aligned beneath it. Only
            // visible while streaming AND a callback is wired.
            if (streaming && !stopped && onStopGenerating != null)
              Padding(
                padding: const EdgeInsets.only(
                  left: AppStyles.spacingXS,
                  top: AppStyles.spacingXS,
                ),
                child: StopStreamingButton(onPressed: onStopGenerating!),
              ),
          ],
        ),
      ),
    );
  }
}

/// A tool-use chip rendered above the assistant text. Shows what the
/// assistant looked at (or is looking at) while answering.
class _ToolEventChip extends StatelessWidget {
  const _ToolEventChip({required this.label, required this.inProgress});
  final String label;
  final bool inProgress;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            inProgress
                ? Icons.auto_awesome_outlined
                : Icons.check_circle_outline_rounded,
            size: 12,
            color: AppColors.textTertiary,
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textTertiary,
                fontWeight: FontWeight.w500,
                height: 1.3,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Markdown stylesheet tuned for the dark assistant bubble. Body matches the
/// previous Text style (16pt, textSecondary, 1.45 line-height). Bold and
/// headings tighten in textPrimary; code keeps a darker chip; links use
/// brand blue. List bullets and numbers stay textTertiary so the structure
/// reads as scaffolding, not signal.
MarkdownStyleSheet _markdownStyle(BuildContext context) {
  const body = TextStyle(
    fontSize: 16,
    color: AppColors.textSecondary,
    height: 1.45,
  );
  return MarkdownStyleSheet(
    p: body,
    pPadding: EdgeInsets.zero,
    strong: body.copyWith(
      color: AppColors.textPrimary,
      fontWeight: FontWeight.w600,
    ),
    em: body.copyWith(fontStyle: FontStyle.italic),
    a: body.copyWith(
      color: AppColors.brandPrimary,
      decoration: TextDecoration.underline,
    ),
    code: const TextStyle(
      fontSize: 14,
      fontFamily: 'monospace',
      color: AppColors.textPrimary,
      backgroundColor: AppColors.backgroundTertiary,
    ),
    codeblockDecoration: BoxDecoration(
      color: AppColors.backgroundTertiary,
      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
    ),
    codeblockPadding: const EdgeInsets.all(AppStyles.spacingM),
    h1: body.copyWith(fontSize: 22, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
    h2: body.copyWith(fontSize: 19, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
    h3: body.copyWith(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
    listBullet: body.copyWith(color: AppColors.textTertiary),
    blockquote: body.copyWith(color: AppColors.textTertiary),
    blockquoteDecoration: BoxDecoration(
      color: AppColors.backgroundPrimary.withValues(alpha: 0.4),
      borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
    ),
    blockquotePadding: const EdgeInsets.all(AppStyles.spacingS),
    horizontalRuleDecoration: BoxDecoration(
      border: Border(
        top: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
      ),
    ),
  );
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

