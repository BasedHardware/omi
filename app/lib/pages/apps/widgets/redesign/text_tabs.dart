import 'package:flutter/material.dart';

/// Two (or more) underlined text tabs.
///
/// Replaces the iOS-default segmented control with a quieter, more designed
/// affordance: just text labels with an underline under the active one.
/// Used on the Apps listing to switch between `Discover` and `Installed`.
class TextTabs<T> extends StatelessWidget {
  final List<TextTabItem<T>> items;
  final T value;
  final ValueChanged<T> onChanged;

  const TextTabs({
    super.key,
    required this.items,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final item in items) _Tab(item: item, active: item.value == value, onTap: () => onChanged(item.value)),
        ],
      ),
    );
  }
}

class _Tab<T> extends StatelessWidget {
  final TextTabItem<T> item;
  final bool active;
  final VoidCallback onTap;

  const _Tab({required this.item, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.only(right: 22),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              item.label,
              style: TextStyle(
                fontSize: 15,
                fontWeight: active ? FontWeight.w600 : FontWeight.w500,
                color: active ? Colors.white : Colors.grey.shade500,
                letterSpacing: -0.2,
              ),
            ),
            const Spacer(),
            AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              height: 2,
              width: active ? _measureLabelWidth(item.label) : 0,
              decoration: BoxDecoration(
                color: const Color(0xFF8B5CF6),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Rough character-width estimate so the underline matches the label.
  // Cheaper than laying out a TextPainter per build; close enough for short
  // labels like "Discover", "Installed".
  double _measureLabelWidth(String label) => label.length * 8.5 + 4;
}

class TextTabItem<T> {
  final String label;
  final T value;
  const TextTabItem({required this.label, required this.value});
}
