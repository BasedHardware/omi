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

class _MemoriesReviewPageState extends State<MemoriesReviewPage> with TickerProviderStateMixin {
  late List<Memory> remainingMemories;
  late List<Memory> displayedMemories;
  MemoryCategory? selectedCategory;
  bool isReviewing = false;
  bool _isProcessing = false;
  bool _isCardView = false; // Default to list view

  // Card swipe state
  double _cardOffset = 0;
  double _cardRotation = 0;
  bool _isDragging = false;
  late AnimationController _animationController;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    remainingMemories = List.from(widget.memories);
    displayedMemories = List.from(remainingMemories);

    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );

    _animation = Tween<double>(
      begin: 0,
      end: 1,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  void _filterByCategory(MemoryCategory? category) {
    setState(() {
      selectedCategory = category;
      displayedMemories = category == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == category).toList();
      // Reset card position when filtering
      _cardOffset = 0;
      _cardRotation = 0;
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

    List<Memory> memoriesToProcess = selectedCategory == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == selectedCategory).toList();

    final count = memoriesToProcess.length;

    // Process memories with a small delay to allow UI to update
    for (var memory in memoriesToProcess) {
      await Future.delayed(const Duration(milliseconds: 20));
      context.read<MemoriesProvider>().reviewMemory(memory, approve, 'review_page_batch');
    }

    setState(() {
      remainingMemories.removeWhere((f) => memoriesToProcess.contains(f));
      displayedMemories = selectedCategory == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == selectedCategory).toList();
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
    context.read<MemoriesProvider>().reviewMemory(memory, approve, 'review_page_single');

    setState(() {
      remainingMemories.remove(memory);
      displayedMemories = selectedCategory == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == selectedCategory).toList();
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

  void _onPanUpdate(DragUpdateDetails details) {
    if (_isProcessing || displayedMemories.isEmpty) return;

    setState(() {
      _cardOffset += details.delta.dx;
      _cardRotation = (_cardOffset / 300) * 0.1;
      _isDragging = true;
    });
  }

  void _onPanEnd(DragEndDetails details) {
    if (_isProcessing || displayedMemories.isEmpty) return;

    const double threshold = 100;

    if (_cardOffset.abs() > threshold) {
      // Swipe detected
      final bool approve = _cardOffset > 0; // Right swipe = approve

      if (displayedMemories.isNotEmpty) {
        _processSingleMemory(displayedMemories.first, approve);
      }

      // Animate card away
      _animationController.forward().then((_) {
        setState(() {
          _cardOffset = 0;
          _cardRotation = 0;
          _isDragging = false;
        });
        _animationController.reset();
      });
    } else {
      // Snap back to center
      _animationController.forward().then((_) {
        setState(() {
          _cardOffset = 0;
          _cardRotation = 0;
          _isDragging = false;
        });
        _animationController.reset();
      });
    }
  }

  Widget _buildCardView() {
    if (displayedMemories.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 48, color: Colors.grey.shade600),
            const SizedBox(height: 16),
            Text(
              selectedCategory == null ? 'All memories have been reviewed' : 'No memories in this category',
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 16,
              ),
            ),
          ],
        ),
      );
    }

    return Stack(
      children: [
        // Instructions
        Positioned(
          top: 20,
          left: 16,
          right: 16,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(Icons.swipe_left, color: Colors.red.shade300, size: 20),
                  const SizedBox(width: 4),
                  Text(
                    'Swipe left to discard',
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
              Row(
                children: [
                  Text(
                    'Swipe right to save',
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Icon(Icons.swipe_right, color: Colors.green.shade300, size: 20),
                ],
              ),
            ],
          ),
        ),

        // Cards stack
        Center(
          child: SizedBox(
            width: MediaQuery.of(context).size.width * 0.9,
            height: MediaQuery.of(context).size.height * 0.6,
            child: Stack(
              children: [
                // Background cards (for depth effect)
                if (displayedMemories.length > 1)
                  Positioned(
                    left: 4,
                    top: 4,
                    right: -4,
                    bottom: -4,
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.grey.shade700,
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),
                if (displayedMemories.length > 2)
                  Positioned(
                    left: 8,
                    top: 8,
                    right: -8,
                    bottom: -8,
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.grey.shade600,
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                  ),

                // Main card
                AnimatedBuilder(
                  animation: _animation,
                  builder: (context, child) {
                    // Safety check to prevent null reference errors
                    if (displayedMemories.isEmpty) {
                      return const SizedBox.shrink();
                    }

                    final double animatedOffset = _isDragging ? _cardOffset : _cardOffset * (1 - _animation.value);
                    final double animatedRotation = _isDragging ? _cardRotation : _cardRotation * (1 - _animation.value);

                    return Transform.translate(
                      offset: Offset(animatedOffset, 0),
                      child: Transform.rotate(
                        angle: animatedRotation,
                        child: GestureDetector(
                          onPanUpdate: _onPanUpdate,
                          onPanEnd: _onPanEnd,
                          child: Stack(
                            children: [
                              Container(
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade900,
                                  borderRadius: BorderRadius.circular(16),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withOpacity(0.3),
                                      blurRadius: 10,
                                      offset: const Offset(0, 5),
                                    ),
                                  ],
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.all(20),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      if (displayedMemories.isNotEmpty) ...[
                                        CategoryChip(
                                          category: displayedMemories.first.category,
                                          showIcon: true,
                                        ),
                                        const SizedBox(height: 16),
                                        Expanded(
                                          child: SingleChildScrollView(
                                            child: Text(
                                              displayedMemories.first.content.decodeString,
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
                                                height: 1.5,
                                              ),
                                            ),
                                          ),
                                        ),
                                      ] else ...[
                                        const Expanded(
                                          child: Center(
                                            child: CircularProgressIndicator(
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                              ),

                              // Swipe overlay
                              if (_isDragging)
                                Container(
                                  decoration: BoxDecoration(
                                    color: _cardOffset > 0 ? Colors.green.withOpacity(0.3) : Colors.red.withOpacity(0.3),
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                  child: Center(
                                    child: Icon(
                                      _cardOffset > 0 ? Icons.check : Icons.close,
                                      size: 80,
                                      color: _cardOffset > 0 ? Colors.green : Colors.red,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ),

        // Action buttons
        Positioned(
          bottom: 40,
          left: 16,
          right: 16,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              FloatingActionButton(
                onPressed: () {
                  if (displayedMemories.isNotEmpty) {
                    _processSingleMemory(displayedMemories.first, false);
                  }
                },
                backgroundColor: Colors.red.shade600,
                child: const Icon(Icons.close, color: Colors.white),
              ),
              FloatingActionButton(
                onPressed: () {
                  if (displayedMemories.isNotEmpty) {
                    _processSingleMemory(displayedMemories.first, true);
                  }
                },
                backgroundColor: Colors.green.shade600,
                child: const Icon(Icons.check, color: Colors.white),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildListView() {
    return displayedMemories.isEmpty
        ? Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.check_circle_outline, size: 48, color: Colors.grey.shade600),
                const SizedBox(height: 16),
                Text(
                  selectedCategory == null ? 'All memories have been reviewed' : 'No memories in this category',
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
                                  color: Colors.purple.shade700,
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
          );
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
          actions: [
            IconButton(
              onPressed: () {
                setState(() {
                  _isCardView = !_isCardView;
                  // Reset card position when switching views
                  _cardOffset = 0;
                  _cardRotation = 0;
                });
              },
              icon: Icon(
                _isCardView ? Icons.view_list : Icons.view_carousel,
                color: Colors.white,
              ),
              tooltip: _isCardView ? 'Switch to List View' : 'Switch to Card View',
            ),
          ],
        ),
        body: Column(
          children: [
            // Category filter chips
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

            // Main content area
            Expanded(
              child: _isCardView ? _buildCardView() : _buildListView(),
            ),

            // Batch actions (only show in list view)
            if (!_isCardView && displayedMemories.isNotEmpty)
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
                                  color: Colors.purple.shade700,
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
