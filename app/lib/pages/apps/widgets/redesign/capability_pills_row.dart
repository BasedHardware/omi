import 'package:flutter/material.dart';

/// Horizontal scrolling capability pills.
///
/// Replaces the carousel of icon tiles per capability with a single pill row
/// the user can use to filter the list down. Each pill is a label only — no
/// editorial imagery, which differentiates from App Store's "Today" cards.
class CapabilityPillsRow extends StatelessWidget {
  final List<CapabilityPill> pills;
  final String? selectedId;
  final ValueChanged<String?> onSelected;

  const CapabilityPillsRow({
    super.key,
    required this.pills,
    required this.selectedId,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    if (pills.isEmpty) return const SizedBox.shrink();
    return SizedBox(
      height: 36,
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        scrollDirection: Axis.horizontal,
        itemCount: pills.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final pill = pills[i];
          final isSelected = pill.id == selectedId;
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onSelected(isSelected ? null : pill.id),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              curve: Curves.easeOut,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: isSelected ? const Color(0xFF8B5CF6) : const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Text(
                pill.label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: isSelected ? Colors.white : Colors.grey.shade300,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class CapabilityPill {
  final String id;
  final String label;
  const CapabilityPill({required this.id, required this.label});
}
