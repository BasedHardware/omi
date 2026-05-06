import 'package:flutter/material.dart';

enum StatusPillTone { success, warning, neutral }

/// Compact status indicator used in row cards.
/// Filled dot + label, soft tinted background.
class StatusPill extends StatelessWidget {
  final String label;
  final StatusPillTone tone;

  const StatusPill({super.key, required this.label, this.tone = StatusPillTone.neutral});

  @override
  Widget build(BuildContext context) {
    final color = _color(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600, letterSpacing: 0.1),
          ),
        ],
      ),
    );
  }

  Color _color(StatusPillTone tone) {
    switch (tone) {
      case StatusPillTone.success:
        return const Color(0xFF6EE7B7);
      case StatusPillTone.warning:
        return const Color(0xFFFBBF24);
      case StatusPillTone.neutral:
        return Colors.grey.shade400;
    }
  }
}
