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
            // No gap between rows: with the surfaces gone the spacing has to
            // come from the rows' own padding, or they read as floating
            // fragments rather than a short list.
            _PromptRow(label: prompt, onTap: () => onSelected(prompt)),
        ],
      ),
    );
  }
}

class _PromptRow extends StatelessWidget {
  const _PromptRow({required this.label, required this.onTap});

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
        // Padding is the tap target, not a visible box. The rounded pill is the
        // composer's shape and stays unique to it — repeating it here made these
        // read as three peers of the input rather than as examples beneath it.
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        color: Colors.transparent,
        child: Text(
          label,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            // With no surface behind it the text carries the whole element, so
            // it lifts slightly — still clearly quieter than the composer.
            color: Colors.white.withValues(alpha: 0.68),
            fontSize: 15,
            fontWeight: FontWeight.w400,
          ),
        ),
      ),
    );
  }
}
