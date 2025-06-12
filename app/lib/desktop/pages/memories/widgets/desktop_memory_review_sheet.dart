import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';

class DesktopMemoryReviewSheet extends StatefulWidget {
  final List<Memory> memories;
  final MemoriesProvider provider;

  const DesktopMemoryReviewSheet({
    super.key,
    required this.memories,
    required this.provider,
  });

  @override
  State<DesktopMemoryReviewSheet> createState() => _DesktopMemoryReviewSheetState();
}

class _DesktopMemoryReviewSheetState extends State<DesktopMemoryReviewSheet> with TickerProviderStateMixin {
  late List<Memory> remainingMemories;
  late List<Memory> displayedMemories;
  MemoryCategory? selectedCategory;
  bool _isProcessing = false;

  // Animation controllers
  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    remainingMemories = List.from(widget.memories);
    displayedMemories = List.from(remainingMemories);

    // Initialize animations
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Start animations
    _fadeController.forward();
    _slideController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _filterByCategory(MemoryCategory? category) {
    setState(() {
      selectedCategory = category;
      displayedMemories = category == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == category).toList();
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

    for (var memory in memoriesToProcess) {
      await Future.delayed(const Duration(milliseconds: 20));
      widget.provider.reviewMemory(memory, approve, 'desktop_review_sheet_batch');
    }

    setState(() {
      remainingMemories.removeWhere((f) => memoriesToProcess.contains(f));
      displayedMemories = selectedCategory == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == selectedCategory).toList();
      _isProcessing = false;
    });

    if (!mounted) return;

    _showSuccessNotification(approve ? 'Saved $count memories' : 'Discarded $count memories');

    if (remainingMemories.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _processSingleMemory(Memory memory, bool approve) async {
    if (_isProcessing) return;

    setState(() => _isProcessing = true);

    widget.provider.reviewMemory(memory, approve, 'desktop_review_sheet_single');

    setState(() {
      remainingMemories.remove(memory);
      displayedMemories = selectedCategory == null ? List.from(remainingMemories) : remainingMemories.where((f) => f.category == selectedCategory).toList();
      _isProcessing = false;
    });

    if (!mounted) return;

    _showSuccessNotification(approve ? 'Memory saved' : 'Memory discarded');

    if (remainingMemories.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _showSuccessNotification(String message) {
    final overlay = Overlay.of(context);
    late OverlayEntry overlayEntry;

    overlayEntry = OverlayEntry(
      builder: (context) => Positioned(
        top: 80,
        right: 40,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.green.shade600,
                  Colors.green.shade700,
                ],
              ),
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 16,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  FontAwesomeIcons.check,
                  color: Colors.white,
                  size: 16,
                ),
                const SizedBox(width: 12),
                Text(
                  message,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    overlay.insert(overlayEntry);

    Future.delayed(const Duration(seconds: 3), () {
      overlayEntry.remove();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 900,
        height: 700,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              ResponsiveHelper.backgroundPrimary,
              ResponsiveHelper.backgroundSecondary.withOpacity(0.9),
            ],
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              blurRadius: 40,
              offset: const Offset(0, 20),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: Stack(
            children: [
              // Animated background pattern
              _buildAnimatedBackground(),

              // Main content
              Container(
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.02),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: FadeTransition(
                  opacity: _fadeAnimation,
                  child: SlideTransition(
                    position: _slideAnimation,
                    child: Column(
                      children: [
                        // Modern header
                        _buildModernHeader(),

                        // Content area
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 32),
                            child: Column(
                              children: [
                                // Category filters
                                _buildCategoryFilters(),

                                const SizedBox(height: 24),

                                // Memories list
                                Expanded(child: _buildMemoriesList()),

                                // Action buttons
                                if (displayedMemories.isNotEmpty) _buildActionButtons(),
                              ],
                            ),
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
      ),
    );
  }

  Widget _buildAnimatedBackground() {
    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topRight,
              radius: 1.5,
              colors: [
                ResponsiveHelper.purplePrimary.withOpacity(0.08 + _pulseAnimation.value * 0.04),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildModernHeader() {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Icon with glassmorphism
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  ResponsiveHelper.purplePrimary.withOpacity(0.2),
                  ResponsiveHelper.purplePrimary.withOpacity(0.1),
                ],
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Icon(
              FontAwesomeIcons.brain,
              color: ResponsiveHelper.purplePrimary,
              size: 24,
            ),
          ),

          const SizedBox(width: 20),

          // Title and subtitle
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Review Memories',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  _getFilterSubtitle(),
                  style: TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),

          // Close button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => Navigator.pop(context),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  FontAwesomeIcons.xmark,
                  color: ResponsiveHelper.textSecondary,
                  size: 18,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryFilters() {
    return Container(
      height: 48,
      child: Row(
        children: [
          Expanded(
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                _buildCategoryFilter(
                  'All Memories',
                  '${remainingMemories.length}',
                  FontAwesomeIcons.layerGroup,
                  selectedCategory == null,
                  () => _filterByCategory(null),
                ),
                const SizedBox(width: 12),
                ...categoryCounts.entries.map((entry) {
                  final category = entry.key;
                  final count = entry.value;
                  String categoryName = category.toString().split('.').last;
                  categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);

                  return Padding(
                    padding: const EdgeInsets.only(right: 12),
                    child: _buildCategoryFilter(
                      categoryName,
                      count.toString(),
                      _getCategoryIcon(category),
                      selectedCategory == category,
                      () => _filterByCategory(category),
                    ),
                  );
                }),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryFilter(String label, String count, IconData icon, bool isSelected, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          decoration: BoxDecoration(
            gradient: isSelected
                ? LinearGradient(
                    colors: [
                      ResponsiveHelper.purplePrimary.withOpacity(0.2),
                      ResponsiveHelper.purplePrimary.withOpacity(0.15),
                    ],
                  )
                : null,
            color: isSelected ? null : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.5) : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
              width: 1.5,
            ),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : [],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 16,
                color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  fontSize: 14,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.2) : ResponsiveHelper.backgroundTertiary.withOpacity(0.8),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  count,
                  style: TextStyle(
                    color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMemoriesList() {
    if (displayedMemories.isEmpty) {
      return _buildEmptyState();
    }

    return ListView.builder(
      itemCount: displayedMemories.length,
      itemBuilder: (context, index) {
        final memory = displayedMemories[index];
        return AnimatedContainer(
          duration: Duration(milliseconds: 300 + (index * 50)),
          curve: Curves.easeOutCubic,
          child: FadeTransition(
            opacity: _fadeAnimation,
            child: SlideTransition(
              position: Tween<Offset>(
                begin: Offset(0, 0.1 + (index * 0.02)),
                end: Offset.zero,
              ).animate(CurvedAnimation(
                parent: _slideController,
                curve: Interval(
                  (index * 0.1).clamp(0.0, 0.8),
                  1.0,
                  curve: Curves.easeOutCubic,
                ),
              )),
              child: _buildMemoryCard(memory, index),
            ),
          ),
        );
      },
    );
  }

  Widget _buildMemoryCard(Memory memory, int index) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
            ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.all(24),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Category indicator
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      _getCategoryColor(memory.category).withOpacity(0.2),
                      _getCategoryColor(memory.category).withOpacity(0.1),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: _getCategoryColor(memory.category).withOpacity(0.3),
                    width: 1,
                  ),
                ),
                child: Icon(
                  _getCategoryIcon(memory.category),
                  color: _getCategoryColor(memory.category),
                  size: 20,
                ),
              ),

              const SizedBox(width: 20),

              // Memory content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Category chip
                    Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: _getCategoryColor(memory.category).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: _getCategoryColor(memory.category).withOpacity(0.3),
                          width: 1,
                        ),
                      ),
                      child: Text(
                        _getCategoryName(memory.category),
                        style: TextStyle(
                          color: _getCategoryColor(memory.category),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),

                    // Memory text
                    Text(
                      memory.content.decodeString,
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 16,
                        height: 1.5,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),

              const SizedBox(width: 20),

              // Action buttons
              Column(
                children: [
                  // Discard button
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _processSingleMemory(memory, false),
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.red.shade500.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.red.shade500.withOpacity(0.3),
                            width: 1,
                          ),
                        ),
                        child: Icon(
                          FontAwesomeIcons.trash,
                          size: 16,
                          color: Colors.red.shade500,
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 12),

                  // Save button
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _processSingleMemory(memory, true),
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              Colors.green.shade500,
                              Colors.green.shade600,
                            ],
                          ),
                          borderRadius: BorderRadius.circular(12),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.green.withOpacity(0.3),
                              blurRadius: 8,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: const Icon(
                          FontAwesomeIcons.check,
                          size: 16,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(48),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
              ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
            ],
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: _pulseController,
              builder: (context, child) {
                return Transform.scale(
                  scale: 1.0 + (_pulseAnimation.value * 0.05),
                  child: Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          ResponsiveHelper.purplePrimary.withOpacity(0.2),
                          ResponsiveHelper.purplePrimary.withOpacity(0.1),
                        ],
                      ),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Icon(
                      FontAwesomeIcons.circleCheck,
                      size: 48,
                      color: ResponsiveHelper.purplePrimary,
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 24),
            Text(
              selectedCategory == null ? '🎉 All memories reviewed!' : '✅ No memories in this category',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 24,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              selectedCategory == null ? 'Great job! You\'ve reviewed all your memories.' : 'All memories in this category have been processed.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 16,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionButtons() {
    return Container(
      margin: const EdgeInsets.only(top: 24, bottom: 24),
      padding: const EdgeInsets.only(top: 24),
      decoration: BoxDecoration(
        border: Border(
          top: BorderSide(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
        ),
      ),
      child: _isProcessing
          ? Center(
              child: Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                        strokeWidth: 2,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Text(
                      'Processing memories...',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            )
          : Row(
              children: [
                // Discard all button
                Expanded(
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _processBatchAction(false),
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        decoration: BoxDecoration(
                          color: Colors.red.shade500.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: Colors.red.shade500.withOpacity(0.3),
                            width: 1.5,
                          ),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              FontAwesomeIcons.trash,
                              size: 18,
                              color: Colors.red.shade500,
                            ),
                            const SizedBox(width: 12),
                            Text(
                              'Discard All',
                              style: TextStyle(
                                color: Colors.red.shade500,
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),

                const SizedBox(width: 16),

                // Save all button
                Expanded(
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _processBatchAction(true),
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              Colors.green.shade500,
                              Colors.green.shade600,
                            ],
                          ),
                          borderRadius: BorderRadius.circular(16),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.green.withOpacity(0.4),
                              blurRadius: 12,
                              offset: const Offset(0, 6),
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(
                              FontAwesomeIcons.check,
                              size: 18,
                              color: Colors.white,
                            ),
                            const SizedBox(width: 12),
                            const Text(
                              'Save All',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  String _getFilterSubtitle() {
    if (selectedCategory == null) {
      return '${displayedMemories.length} memories awaiting your review';
    }

    String categoryName = _getCategoryName(selectedCategory!);
    return '${displayedMemories.length} $categoryName memories to review';
  }

  String _getCategoryName(MemoryCategory category) {
    switch (category) {
      case MemoryCategory.interesting:
        return 'Interesting';
      case MemoryCategory.system:
        return 'System';
      default:
        return 'Unknown';
    }
  }

  Color _getCategoryColor(MemoryCategory category) {
    switch (category) {
      case MemoryCategory.interesting:
        return ResponsiveHelper.purplePrimary;
      case MemoryCategory.system:
        return Colors.orange;
      default:
        return ResponsiveHelper.textSecondary;
    }
  }

  IconData _getCategoryIcon(MemoryCategory category) {
    switch (category) {
      case MemoryCategory.interesting:
        return FontAwesomeIcons.lightbulb;
      case MemoryCategory.system:
        return FontAwesomeIcons.gear;
      default:
        return FontAwesomeIcons.noteSticky;
    }
  }
}
