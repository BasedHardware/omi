import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

import 'widgets/category_chip.dart';

class MemoriesReviewPage extends StatefulWidget {
  final List<Memory> memories;

  const MemoriesReviewPage({
    super.key,
    required this.memories,
  });

  @override
  State<MemoriesReviewPage> createState() => _MemoriesReviewPageState();
}

class _MemoriesReviewPageState extends State<MemoriesReviewPage> {
  late List<Memory> remainingMemories;
  late List<Memory> displayedMemories;
  MemoryCategory? selectedCategory;
  bool isReviewing = false;
  bool _isProcessing = false;

  @override
  void initState() {
    super.initState();
    remainingMemories = List.from(widget.memories);
    displayedMemories = List.from(remainingMemories);
  }

  void _filterByCategory(MemoryCategory? category) {
    setState(() {
      selectedCategory = category;
      displayedMemories = category == null
          ? List.from(remainingMemories)
          : remainingMemories.where((f) => f.category == category).toList();
    });
  }

  Map<MemoryCategory, int> get categoryCounts {
    var counts = <MemoryCategory, int>{};
    for (var memory in remainingMemories) {
      counts[memory.category] = (counts[memory.category] ?? 0) + 1;
    }
    return counts;
  }

  void _processBatchAction(bool approve) async {
    if (_isProcessing) return;

    setState(() => _isProcessing = true);

    List<Memory> memoriesToProcess = selectedCategory == null
        ? List.from(remainingMemories)
        : remainingMemories.where((f) => f.category == selectedCategory).toList();

    final count = memoriesToProcess.length;

    // Process memories with a small delay to allow UI to update
    for (var memory in memoriesToProcess) {
      await Future.delayed(const Duration(milliseconds: 20));
      context.read<MemoriesProvider>().reviewMemory(memory, approve);
    }

    setState(() {
      remainingMemories.removeWhere((f) => memoriesToProcess.contains(f));
      displayedMemories = selectedCategory == null
          ? List.from(remainingMemories)
          : remainingMemories.where((f) => f.category == selectedCategory).toList();
      _isProcessing = false;
    });

    // Show feedback
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Saved $count memories' : 'Discarded $count memories',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.grey.shade800,
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      ),
    );

    if (remainingMemories.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _processSingleMemory(Memory memory, bool approve) async {
    if (_isProcessing) return;

    setState(() => _isProcessing = true);

    // Process the single memory
    context.read<MemoriesProvider>().reviewMemory(memory, approve);

    setState(() {
      remainingMemories.remove(memory);
      displayedMemories = selectedCategory == null
          ? List.from(remainingMemories)
          : remainingMemories.where((f) => f.category == selectedCategory).toList();
      _isProcessing = false;
    });

    // Show feedback
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Memory saved' : 'Memory discarded',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Colors.grey.shade800,
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      ),
    );

    if (remainingMemories.isEmpty) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const Text('Review Memories'),
              Text(
                _getFilterSubtitle(),
                style: TextStyle(
                  fontSize: 13,
                  color: Colors.grey.shade400,
                  fontWeight: FontWeight.normal,
                ),
              ),
            ],
          ),
        ),
        body: Column(
          children: [
            Container(
              height: 46,
              margin: const EdgeInsets.only(top: 4, bottom: 8),
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: Text(
                        'All (${remainingMemories.length})',
                        style: TextStyle(
                          color: selectedCategory == null ? Colors.black : Colors.white70,
                          fontWeight: selectedCategory == null ? FontWeight.w600 : FontWeight.normal,
                          fontSize: 13,
                        ),
                      ),
                      selected: selectedCategory == null,
                      onSelected: (_) => _filterByCategory(null),
                      backgroundColor: Colors.grey.shade800,
                      selectedColor: Colors.white,
                      checkmarkColor: Colors.black,
                      showCheckmark: false,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    ),
                  ),
                  ...categoryCounts.entries.map((entry) {
                    final category = entry.key;
                    final count = entry.value;

                    // Format category name to be more concise
                    String categoryName = category.toString().split('.').last;
                    // Capitalize first letter only
                    categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);

                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(
                          '$categoryName ($count)',
                          style: TextStyle(
                            color: selectedCategory == category ? Colors.black : Colors.white70,
                            fontWeight: selectedCategory == category ? FontWeight.w600 : FontWeight.normal,
                            fontSize: 13,
                          ),
                        ),
                        selected: selectedCategory == category,
                        onSelected: (_) => _filterByCategory(category),
                        backgroundColor: Colors.grey.shade800,
                        selectedColor: Colors.white,
                        checkmarkColor: Colors.black,
                        showCheckmark: false,
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      ),
                    );
                  }),
                ],
              ),
            ),
            Expanded(
              child: displayedMemories.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.check_circle_outline, size: 48, color: Colors.grey.shade600),
                          const SizedBox(height: 16),
                          Text(
                            selectedCategory == null
                                ? 'All memories have been reviewed'
                                : 'No memories in this category',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
                      itemCount: displayedMemories.length,
                      itemBuilder: (context, index) {
                        final memory = displayedMemories[index];
                        return Container(
                          margin: const EdgeInsets.only(bottom: 10),
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.all(14),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    CategoryChip(
                                      category: memory.category,
                                      showIcon: true,
                                    ),
                                    const SizedBox(height: 10),
                                    Text(
                                      memory.content.decodeString,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 15,
                                        height: 1.4,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              Container(
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade800,
                                  borderRadius: const BorderRadius.vertical(
                                    bottom: Radius.circular(12),
                                  ),
                                ),
                                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: GestureDetector(
                                        onTap: () => _processSingleMemory(memory, false),
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(vertical: 8),
                                          decoration: BoxDecoration(
                                            color: Colors.white.withOpacity(0.1),
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: const Row(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Icon(Icons.delete_outline, size: 16, color: Colors.white70),
                                              SizedBox(width: 6),
                                              Text(
                                                'Discard',
                                                style: TextStyle(
                                                  color: Colors.white70,
                                                  fontSize: 13,
                                                  fontWeight: FontWeight.w500,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: GestureDetector(
                                        onTap: () => _processSingleMemory(memory, true),
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(vertical: 8),
                                          decoration: BoxDecoration(
                                            color: Colors.blue.shade700,
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: const Row(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Icon(Icons.check, size: 16, color: Colors.white),
                                              SizedBox(width: 6),
                                              Text(
                                                'Save',
                                                style: TextStyle(
                                                  color: Colors.white,
                                                  fontSize: 13,
                                                  fontWeight: FontWeight.w500,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
            ),
            if (displayedMemories.isNotEmpty)
              Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  border: Border(
                    top: BorderSide(
                      color: Colors.white.withOpacity(0.1),
                      width: 1,
                    ),
                  ),
                ),
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                child: _isProcessing
                    ? const Center(
                        child: Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            strokeWidth: 3,
                          ),
                        ),
                      )
                    : Row(
                        children: [
                          Expanded(
                            child: GestureDetector(
                              onTap: () => _processBatchAction(false),
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                alignment: Alignment.center,
                                child: const Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(Icons.delete_outline, size: 18, color: Colors.white70),
                                    SizedBox(width: 8),
                                    Text(
                                      'Discard All',
                                      style: TextStyle(
                                        color: Colors.white70,
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: GestureDetector(
                              onTap: () => _processBatchAction(true),
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                decoration: BoxDecoration(
                                  color: Colors.blue.shade700,
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                alignment: Alignment.center,
                                child: const Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(Icons.check, size: 18, color: Colors.white),
                                    SizedBox(width: 8),
                                    Text(
                                      'Save All',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
              ),
          ],
        ),
      );
    });
  }

  String _getFilterSubtitle() {
    if (selectedCategory == null) {
      return '${displayedMemories.length} memories to review';
    }

    String categoryName = selectedCategory.toString().split('.').last;
    categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);

    return '${displayedMemories.length} ${categoryName} memories';
  }
}
