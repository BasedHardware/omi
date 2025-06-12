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

class _DesktopMemoryReviewSheetState extends State<DesktopMemoryReviewSheet> {
  late List<Memory> remainingMemories;
  late List<Memory> displayedMemories;
  MemoryCategory? selectedCategory;
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

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Saved $count memories' : 'Discarded $count memories',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );

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

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          approve ? 'Memory saved' : 'Memory discarded',
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );

    if (remainingMemories.isEmpty) {
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 800,
        height: 600,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 30,
              offset: const Offset(0, 15),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Icon(
                  FontAwesomeIcons.magnifyingGlass,
                  color: ResponsiveHelper.textSecondary,
                  size: 18,
                ),
                const SizedBox(width: 12),
                Text(
                  'Review Memories',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: Icon(
                    FontAwesomeIcons.xmark,
                    color: ResponsiveHelper.textSecondary,
                    size: 16,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 8),

            Text(
              _getFilterSubtitle(),
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
              ),
            ),

            const SizedBox(height: 24),

            // Category filters
            Container(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  _buildCategoryFilter(
                    'All (${remainingMemories.length})',
                    selectedCategory == null,
                    () => _filterByCategory(null),
                  ),
                  const SizedBox(width: 8),
                  ...categoryCounts.entries.map((entry) {
                    final category = entry.key;
                    final count = entry.value;
                    String categoryName = category.toString().split('.').last;
                    categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);

                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: _buildCategoryFilter(
                        '$categoryName ($count)',
                        selectedCategory == category,
                        () => _filterByCategory(category),
                      ),
                    );
                  }),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Memories list
            Expanded(
              child: displayedMemories.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            FontAwesomeIcons.circleCheck,
                            size: 48,
                            color: ResponsiveHelper.textTertiary,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            selectedCategory == null ? 'All memories have been reviewed' : 'No memories in this category',
                            style: TextStyle(
                              color: ResponsiveHelper.textSecondary,
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                    )
                  : ListView.builder(
                      itemCount: displayedMemories.length,
                      itemBuilder: (context, index) {
                        final memory = displayedMemories[index];
                        return Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: Material(
                            color: Colors.transparent,
                            child: Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                                  width: 1,
                                ),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withOpacity(0.05),
                                    blurRadius: 8,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  // Category icon
                                  Container(
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(
                                      color: _getCategoryColor(memory.category).withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Icon(
                                      _getCategoryIcon(memory.category),
                                      color: _getCategoryColor(memory.category),
                                      size: 16,
                                    ),
                                  ),

                                  const SizedBox(width: 12),

                                  // Memory content
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          memory.content.decodeString,
                                          style: TextStyle(
                                            color: ResponsiveHelper.textPrimary,
                                            fontSize: 15,
                                            height: 1.4,
                                          ),
                                          maxLines: 3,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ],
                                    ),
                                  ),

                                  const SizedBox(width: 12),

                                  // Action buttons
                                  Row(
                                    children: [
                                      // Discard button
                                      Material(
                                        color: Colors.transparent,
                                        child: InkWell(
                                          onTap: () => _processSingleMemory(memory, false),
                                          borderRadius: BorderRadius.circular(8),
                                          child: Container(
                                            padding: const EdgeInsets.all(8),
                                            decoration: BoxDecoration(
                                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                                              borderRadius: BorderRadius.circular(8),
                                            ),
                                            child: Icon(
                                              FontAwesomeIcons.trash,
                                              size: 14,
                                              color: ResponsiveHelper.textSecondary,
                                            ),
                                          ),
                                        ),
                                      ),

                                      const SizedBox(width: 8),

                                      // Save button
                                      Material(
                                        color: Colors.transparent,
                                        child: InkWell(
                                          onTap: () => _processSingleMemory(memory, true),
                                          borderRadius: BorderRadius.circular(8),
                                          child: Container(
                                            padding: const EdgeInsets.all(8),
                                            decoration: BoxDecoration(
                                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                                              borderRadius: BorderRadius.circular(8),
                                            ),
                                            child: Icon(
                                              FontAwesomeIcons.check,
                                              size: 14,
                                              color: ResponsiveHelper.textPrimary,
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
                      },
                    ),
            ),

            // Bottom actions
            if (displayedMemories.isNotEmpty) ...[
              const SizedBox(height: 16),
              Container(
                decoration: BoxDecoration(
                  border: Border(
                    top: BorderSide(
                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                      width: 1,
                    ),
                  ),
                ),
                padding: const EdgeInsets.only(top: 16),
                child: _isProcessing
                    ? Center(
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.textSecondary),
                            strokeWidth: 2,
                          ),
                        ),
                      )
                    : Row(
                        children: [
                          Expanded(
                            child: Material(
                              color: Colors.transparent,
                              child: InkWell(
                                onTap: () => _processBatchAction(false),
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(vertical: 12),
                                  decoration: BoxDecoration(
                                    color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                                      width: 1,
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(
                                        FontAwesomeIcons.trash,
                                        size: 16,
                                        color: ResponsiveHelper.textSecondary,
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        'Discard All',
                                        style: TextStyle(
                                          color: ResponsiveHelper.textSecondary,
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Material(
                              color: Colors.transparent,
                              child: InkWell(
                                onTap: () => _processBatchAction(true),
                                borderRadius: BorderRadius.circular(12),
                                child: Container(
                                  padding: const EdgeInsets.symmetric(vertical: 12),
                                  decoration: BoxDecoration(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(
                                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                                      width: 1,
                                    ),
                                    boxShadow: [
                                      BoxShadow(
                                        color: Colors.black.withOpacity(0.05),
                                        blurRadius: 8,
                                        offset: const Offset(0, 2),
                                      ),
                                    ],
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(
                                        FontAwesomeIcons.check,
                                        size: 16,
                                        color: ResponsiveHelper.textPrimary,
                                      ),
                                      const SizedBox(width: 8),
                                      Text(
                                        'Save All',
                                        style: TextStyle(
                                          color: ResponsiveHelper.textPrimary,
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500,
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
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryFilter(String label, bool isSelected, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? Colors.white : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isSelected ? ResponsiveHelper.backgroundTertiary.withOpacity(0.5) : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.05),
                      blurRadius: 4,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Text(
            label,
            style: TextStyle(
              color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
              fontSize: 12,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCategoryChip(MemoryCategory category) {
    Color categoryColor;
    IconData categoryIcon;
    String categoryName;

    switch (category) {
      case MemoryCategory.interesting:
        categoryColor = ResponsiveHelper.purplePrimary;
        categoryIcon = FontAwesomeIcons.lightbulb;
        categoryName = 'Interesting';
        break;
      case MemoryCategory.system:
        categoryColor = Colors.orange;
        categoryIcon = FontAwesomeIcons.gear;
        categoryName = 'System';
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: categoryColor.withOpacity(0.2),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: categoryColor.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            categoryIcon,
            size: 12,
            color: categoryColor,
          ),
          const SizedBox(width: 4),
          Text(
            categoryName,
            style: TextStyle(
              color: categoryColor,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  String _getFilterSubtitle() {
    if (selectedCategory == null) {
      return '${displayedMemories.length} memories to review';
    }

    String categoryName = selectedCategory.toString().split('.').last;
    categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);
    return '${displayedMemories.length} $categoryName memories to review';
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
