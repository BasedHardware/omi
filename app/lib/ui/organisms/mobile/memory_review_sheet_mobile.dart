import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';

class MobileMemoryReviewSheet extends StatelessWidget {
  final List<Memory> memories;
  final MemoriesProvider provider;
  final VoidCallback onClose;

  const MobileMemoryReviewSheet({
    super.key,
    required this.memories,
    required this.provider,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    // simple bottom-sheet placeholder
    return BottomSheet(
      onClosing: onClose,
      builder: (_) => Center(
        child: Text(
          'Review ${memories.length} memories\n(Mobile UI coming soon)',
          style: const TextStyle(color: Colors.white),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
