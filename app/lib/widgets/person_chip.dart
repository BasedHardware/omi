import 'package:flutter/material.dart';

class PersonChip extends StatelessWidget {
  final String personName;
  final bool isSelected;
  final Function(bool) onSelected;
  final bool isAddButton;

  const PersonChip({
    super.key,
    required this.personName,
    required this.isSelected,
    required this.onSelected,
    this.isAddButton = false,
  });

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      label: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (isAddButton) const Icon(Icons.add, size: 16),
          if (isAddButton) const SizedBox(width: 4),
          Text(
            personName,
            style: const TextStyle(fontSize: 12),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
      selected: isSelected,
      onSelected: onSelected,
      showCheckmark: !isAddButton,
      selectedColor: Theme.of(context).colorScheme.secondary,
      checkmarkColor: Colors.white,
      backgroundColor: Colors.grey.shade800.withOpacity(0.6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: isSelected ? Theme.of(context).colorScheme.secondary : Colors.transparent,
          width: 1,
        ),
      ),
    );
  }
}
