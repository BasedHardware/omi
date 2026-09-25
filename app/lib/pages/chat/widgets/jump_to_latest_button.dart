import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Compact "Latest" chip. Sized to its child so a Stack can place it over the
/// transcript without a full-width hit-test absorber covering citation cards.
class ChatJumpToLatestButton extends StatelessWidget {
  const ChatJumpToLatestButton({super.key, required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Semantics(
        label: label,
        button: true,
        child: Tooltip(
          message: label,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: OmiRadius.pillAll,
              onTap: onTap,
              child: Container(
                // 11 + 22pt glyph + 11 keeps the chip at the 44pt minimum target.
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                decoration: BoxDecoration(
                  color: OmiColors.surface2.withValues(alpha: 0.95),
                  borderRadius: OmiRadius.pillAll,
                  border: Border.all(color: Colors.white.withValues(alpha: 0.18), width: 1),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.28), blurRadius: 12, offset: const Offset(0, 4)),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.keyboard_arrow_down_rounded, color: OmiColors.textPrimary, size: 22),
                    const SizedBox(width: 6),
                    Text(
                      label,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
