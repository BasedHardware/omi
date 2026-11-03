import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// A neutral square tile with a short mark for an app or agent ("GPT", "Mu"). Colour stays for
/// state (INV-UI-1), so every tile is the same surface; the name beside it carries the identity.
class AgentMonogram extends StatelessWidget {
  const AgentMonogram(this.mark, {super.key, this.icon, this.size = 32});

  final String mark;
  final IconData? icon;
  final double size;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
        child: icon != null
            ? Icon(icon, size: size * 0.55, color: OmiColors.textPrimary)
            : Text(
                mark,
                maxLines: 1,
                style: OmiType.footnote.copyWith(fontWeight: FontWeight.w700, color: OmiColors.textPrimary),
              ),
      ),
    );
  }
}

/// One numbered step in a setup sheet.
class AgentSetupStep extends StatelessWidget {
  const AgentSetupStep({super.key, required this.number, required this.title, required this.body});

  final int number;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ExcludeSemantics(
          child: Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
            child: Text('$number', style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
          ),
        ),
        const SizedBox(width: OmiSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            ],
          ),
        ),
      ],
    );
  }
}

/// A read-only block of prompt text, scrollable when long.
class AgentPromptPreview extends StatelessWidget {
  const AgentPromptPreview({super.key, required this.prompt, this.maxHeight = 220});

  final String prompt;
  final double maxHeight;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxHeight: maxHeight),
      decoration: BoxDecoration(
        color: OmiColors.surface0,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Scrollbar(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Text(
            prompt,
            style: OmiType.footnote.copyWith(
              fontFamily: 'monospace',
              fontFamilyFallback: const ['Menlo', 'Courier'],
              height: 1.45,
              color: OmiColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}
