import 'package:flutter/material.dart';

/// Segmented control for the Apps listing — replaces the App-Store-shaped
/// expanding-pill filter row.
///
/// Three mutually-exclusive options (All / Connected / Mine) styled as a
/// single rounded container with a sliding selection background.
class SegmentedFilter<T> extends StatelessWidget {
  final List<SegmentedFilterItem<T>> items;
  final T value;
  final ValueChanged<T> onChanged;

  const SegmentedFilter({
    super.key,
    required this.items,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 36,
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(10),
      ),
      padding: const EdgeInsets.all(3),
      child: Row(
        children: [
          for (final item in items)
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onChanged(item.value),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  curve: Curves.easeOut,
                  decoration: BoxDecoration(
                    color: item.value == value ? Colors.white.withValues(alpha: 0.10) : Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    item.label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: item.value == value ? Colors.white : Colors.grey.shade400,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class SegmentedFilterItem<T> {
  final String label;
  final T value;
  const SegmentedFilterItem({required this.label, required this.value});
}
