import 'package:flutter/material.dart';

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
              borderRadius: BorderRadius.circular(24),
              onTap: onTap,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25).withValues(alpha: 0.95),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.18), width: 1),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.28), blurRadius: 12, offset: const Offset(0, 4)),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.keyboard_arrow_down_rounded, color: Colors.white, size: 22),
                    const SizedBox(width: 6),
                    Text(
                      label,
                      style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
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
