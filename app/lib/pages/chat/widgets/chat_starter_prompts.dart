import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Example questions shown under the composer before a chat has started.
///
/// They exist to answer "what can I even ask?" — the hardest moment for an
/// assistant whose value isn't visible until you've used it. Tapping one sends
/// it, so the first question costs a tap rather than a decision.
///
/// The set is deliberately fixed and generic: it must read sensibly for a
/// brand-new account with no history *and* for someone with months of it.
/// Nothing here names a person, project, or date, and nothing depends on data
/// that may not exist yet — an empty answer to a suggestion the app itself
/// proposed is worse than not suggesting.
class ChatStarterPrompts extends StatelessWidget {
  const ChatStarterPrompts({super.key, required this.onSelected});

  /// Sends the tapped prompt as a message.
  final void Function(String prompt) onSelected;

  static const List<String> prompts = [
    'Summarize my day',
    'What have I been spending my time on?',
  ];

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final prompt in prompts)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _PromptChip(label: prompt, onTap: () => onSelected(prompt)),
            ),
        ],
      ),
    );
  }
}

class _PromptChip extends StatelessWidget {
  const _PromptChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
        decoration: BoxDecoration(
          // Filled, not outlined: a hairline border is harder to pick out than a
          // soft surface, and gave these the look of controls rather than
          // suggestions. The fill sits between the page (black) and the
          // composer (#1F1F25) so they read as clearly subordinate to the input
          // they sit beneath — present, but never competing with it.
          color: const Color(0xFF131317),
          borderRadius: BorderRadius.circular(22),
        ),
        child: Text(
          label,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            // A step quieter than the composer's placeholder, so the ranking
            // holds on the text as well as the surface.
            color: Colors.white.withValues(alpha: 0.62),
            fontSize: 14,
            fontWeight: FontWeight.w400,
          ),
        ),
      ),
    );
  }
}
