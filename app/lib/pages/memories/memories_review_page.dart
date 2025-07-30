import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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
  bool _isCardView = true; // Default to card view
  int currentCardIndex = 0;

  // Card swipe state
  double _cardOffset = 0;
  double _cardRotation = 0;
  bool _isDragging = false;

  // Animation controllers
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
      currentCardIndex = 0;
      // Reset swipe state
      _cardOffset = 0;
      _cardRotation = 0;
      _isDragging = false;
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
      currentCardIndex = 0;
      // Reset swipe state
      _cardOffset = 0;
      _cardRotation = 0;
      _isDragging = false;
    });

    // Show feedback
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Saved $count memories' : 'Discarded $count memories',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Color(0xFF35343B),
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

      // Adjust current card index if we're in card view
      if (_isCardView && currentCardIndex >= displayedMemories.length && displayedMemories.isNotEmpty) {
        currentCardIndex = displayedMemories.length - 1;
      }

      // Reset swipe state
      _cardOffset = 0;
      _cardRotation = 0;
      _isDragging = false;
    });

    // Show feedback
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Memory saved' : 'Memory discarded',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: Color(0xFF35343B),
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

  void _animateButtonPress(bool approve) async {
    if (_isProcessing || displayedMemories.isEmpty) return;

    // Set the swipe animation state
    setState(() {
      _cardOffset = approve ? 200.0 : -200.0; // Simulate swipe direction
      _cardRotation = (approve ? 200.0 : -200.0) / 300 * 0.1; // Same rotation calculation as swipe
      _isDragging = true;
    });

    // Wait a bit for the animation to be visible
    await Future.delayed(const Duration(milliseconds: 250));

    // Animate the card away
    await _animationController.forward();

    // Process the memory
    if (currentCardIndex < displayedMemories.length) {
      _processSingleMemory(displayedMemories[currentCardIndex], approve);
    }

    // Reset animation
    _animationController.reset();
  }

  void _nextCard() {
    if (currentCardIndex < displayedMemories.length - 1) {
      setState(() {
        currentCardIndex++;
      });
    }
  }

  void _previousCard() {
    if (currentCardIndex > 0) {
      setState(() {
        currentCardIndex--;
      });
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

      if (currentCardIndex < displayedMemories.length) {
        _processSingleMemory(displayedMemories[currentCardIndex], approve);
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

  String _getFilterSubtitle() {
    final totalCount = remainingMemories.length;
    final displayedCount = displayedMemories.length;

    if (selectedCategory != null) {
      return '$displayedCount of $totalCount memories';
    }
    return '$totalCount memories to review';
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

    final currentMemory = displayedMemories[currentCardIndex];

    return Padding(
      padding: const EdgeInsets.fromLTRB(16.0, 0, 16.0, 16.0),
      child: Column(
        children: [
          // Card content with swipe gestures
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0), // Extra padding to prevent clipping
              child: Center(
                child: SizedBox(
                  width: MediaQuery.of(context).size.width * 0.95,
                  height: MediaQuery.of(context).size.height * 0.55,
                  child: Stack(
                    clipBehavior: Clip.none, // Allow overflow
                    children: [
                      // Background cards (stack effect) - positioned to be visible
                      if (currentCardIndex + 2 < displayedMemories.length)
                        Positioned(
                          left: 12,
                          top: 16,
                          right: -12,
                          bottom: -20,
                          child: Container(
                            decoration: BoxDecoration(
                              color: Colors.grey.shade600,
                              borderRadius: BorderRadius.circular(16),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.2),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                            ),
                          ),
                        ),

                      // Second card (next card) - positioned to be visible
                      if (currentCardIndex + 1 < displayedMemories.length)
                        Positioned(
                          left: 6,
                          top: 8,
                          right: -6,
                          bottom: -10,
                          child: Container(
                            padding: const EdgeInsets.all(24),
                            decoration: BoxDecoration(
                              color: Colors.grey.shade700,
                              borderRadius: BorderRadius.circular(16),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.25),
                                  blurRadius: 8,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                // Next memory content (preview)
                                Expanded(
                                  child: Center(
                                    child: SingleChildScrollView(
                                      child: Text(
                                        displayedMemories[currentCardIndex + 1].content.decodeString,
                                        style: TextStyle(
                                          color: Colors.white.withOpacity(0.8),
                                          fontSize: 20,
                                          height: 1.5,
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                                  ),
                                ),

                                const SizedBox(height: 16),

                                // Next category chip
                                CategoryChip(
                                  category: displayedMemories[currentCardIndex + 1].category,
                                  showIcon: true,
                                ),
                              ],
                            ),
                          ),
                        ),

                      // Top card (current card with swipe) - positioned normally
                      Positioned(
                        left: 0,
                        top: 0,
                        right: 0,
                        bottom: 0,
                        child: AnimatedBuilder(
                          animation: _animation,
                          builder: (context, child) {
                            final double animatedOffset = _isDragging ? _cardOffset : _cardOffset * (1 - _animation.value);
                            final double animatedRotation = _isDragging ? _cardRotation : _cardRotation * (1 - _animation.value);

                            return Transform.translate(
                              offset: Offset(animatedOffset, 0),
                              child: Transform.rotate(
                                angle: animatedRotation,
                                child: GestureDetector(
                                  onPanUpdate: _onPanUpdate,
                                  onPanEnd: _onPanEnd,
                                  child: Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(24),
                                    decoration: BoxDecoration(
                                      color: _isDragging ? (_cardOffset > 0 ? const Color(0xFF08A25C) : const Color(0xFFE0582F)) : Color(0xFF35343B),
                                      borderRadius: BorderRadius.circular(16),
                                      boxShadow: [
                                        BoxShadow(
                                          color: Colors.black.withOpacity(0.3),
                                          blurRadius: 10,
                                          offset: const Offset(0, 4),
                                        ),
                                      ],
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.center,
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        // Memory content
                                        Expanded(
                                          child: Center(
                                            child: SingleChildScrollView(
                                              child: Text(
                                                currentMemory.content.decodeString,
                                                style: const TextStyle(
                                                  color: Colors.white,
                                                  fontSize: 20,
                                                  height: 1.5,
                                                ),
                                                textAlign: TextAlign.center,
                                              ),
                                            ),
                                          ),
                                        ),

                                        const SizedBox(height: 16),

                                        // Category chip
                                        CategoryChip(
                                          category: currentMemory.category,
                                          showIcon: true,
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Action buttons with centered progress indicator
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                // Discard button
                Column(
                  children: [
                    Container(
                      width: 70,
                      height: 70,
                      child: FloatingActionButton(
                        onPressed: _isProcessing ? null : () => _animateButtonPress(false),
                        backgroundColor: const Color(0xFFE0582F),
                        heroTag: "discard",
                        elevation: 4,
                        child: FaIcon(
                          FontAwesomeIcons.trashCan,
                          color: Colors.white,
                          size: 24,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Discard',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),

                // Progress indicator (centered)
                Text(
                  '${currentCardIndex + 1} / ${displayedMemories.length}',
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),

                // Save button
                Column(
                  children: [
                    Container(
                      width: 70,
                      height: 70,
                      child: FloatingActionButton(
                        onPressed: _isProcessing ? null : () => _animateButtonPress(true),
                        backgroundColor: const Color(0xFF08A25C),
                        heroTag: "save",
                        elevation: 4,
                        child: FaIcon(
                          FontAwesomeIcons.check,
                          color: Colors.white,
                          size: 24,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Save',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // Bottom spacing
          const SizedBox(height: 30),
        ],
      ),
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
        : Column(
            children: [
              // Memory list
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: displayedMemories.length,
                  itemBuilder: (context, index) {
                    final memory = displayedMemories[index];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Color(0xFF35343B),
                        borderRadius: BorderRadius.circular(12),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.2),
                            blurRadius: 4,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Memory content
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  memory.content.decodeString,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 15,
                                    height: 1.4,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                CategoryChip(
                                  category: memory.category,
                                  showIcon: true,
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(width: 12),

                          // Action buttons
                          Row(
                            children: [
                              // Discard button
                              Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade700,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: IconButton(
                                  onPressed: _isProcessing ? null : () => _processSingleMemory(memory, false),
                                  icon: FaIcon(
                                    FontAwesomeIcons.trashCan,
                                    color: const Color(0xFFE0582F),
                                    size: 16,
                                  ),
                                  padding: EdgeInsets.zero,
                                ),
                              ),

                              const SizedBox(width: 8),

                              // Save button
                              Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade700,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: IconButton(
                                  onPressed: _isProcessing ? null : () => _processSingleMemory(memory, true),
                                  icon: FaIcon(
                                    FontAwesomeIcons.check,
                                    color: const Color(0xFF08A25C),
                                    size: 16,
                                  ),
                                  padding: EdgeInsets.zero,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),

              // Bottom action buttons
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  border: Border(
                    top: BorderSide(
                      color: Colors.grey.shade700,
                      width: 1,
                    ),
                  ),
                ),
                child: Row(
                  children: [
                    // Discard all button
                    Expanded(
                      child: Container(
                        height: 56,
                        margin: const EdgeInsets.only(right: 8),
                        child: ElevatedButton(
                          onPressed: _isProcessing ? null : () => _processBatchAction(false),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFFE0582F),
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 2,
                          ),
                          child: Text(
                            'Discard all',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),

                    // Save all button
                    Expanded(
                      child: Container(
                        height: 56,
                        margin: const EdgeInsets.only(left: 8),
                        child: ElevatedButton(
                          onPressed: _isProcessing ? null : () => _processBatchAction(true),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF08A25C),
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 2,
                          ),
                          child: Text(
                            'Save all',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: _isDragging ? (_cardOffset > 0 ? const Color(0xFFC8D8B2) : const Color(0xFFD2B6AD)) : Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          title: const Text('Facts review'),
          actions: [
            // Filter selector
            PopupMenuButton<String>(
              onSelected: (value) {
                switch (value) {
                  case 'all':
                    _filterByCategory(null);
                    break;
                  case 'system':
                    _filterByCategory(MemoryCategory.system);
                    break;
                  case 'interesting':
                    _filterByCategory(MemoryCategory.interesting);
                    break;
                }
              },
              itemBuilder: (context) => [
                PopupMenuItem(
                  value: 'all',
                  child: Row(
                    children: [
                      Icon(
                        selectedCategory == null ? Icons.check : Icons.circle_outlined,
                        color: selectedCategory == null ? Colors.blue : Colors.grey,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text('All (${remainingMemories.length})'),
                    ],
                  ),
                ),
                PopupMenuItem(
                  value: 'system',
                  child: Row(
                    children: [
                      Icon(
                        selectedCategory == MemoryCategory.system ? Icons.check : Icons.circle_outlined,
                        color: selectedCategory == MemoryCategory.system ? Colors.blue : Colors.grey,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text('System (${categoryCounts[MemoryCategory.system] ?? 0})'),
                    ],
                  ),
                ),
                PopupMenuItem(
                  value: 'interesting',
                  child: Row(
                    children: [
                      Icon(
                        selectedCategory == MemoryCategory.interesting ? Icons.check : Icons.circle_outlined,
                        color: selectedCategory == MemoryCategory.interesting ? Colors.blue : Colors.grey,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text('Interesting (${categoryCounts[MemoryCategory.interesting] ?? 0})'),
                    ],
                  ),
                ),
              ],
              icon: Icon(
                Icons.filter_list,
                color: Colors.white,
              ),
              tooltip: 'Filter memories',
            ),

            // View toggle
            IconButton(
              onPressed: () {
                setState(() {
                  _isCardView = !_isCardView;
                  currentCardIndex = 0;
                  // Reset swipe state when switching views
                  _cardOffset = 0;
                  _cardRotation = 0;
                  _isDragging = false;
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
        body: _isProcessing
            ? const Center(
                child: CircularProgressIndicator(
                  color: Colors.white,
                ),
              )
            : _isCardView
                ? _buildCardView()
                : _buildListView(),
      );
    });
  }
}
