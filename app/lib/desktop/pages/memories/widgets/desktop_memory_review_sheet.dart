import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';
import 'package:omi/ui/molecules/omi_panel_header.dart';
import 'package:omi/ui/atoms/omi_loading_badge.dart';

class DesktopMemoryReviewSheet extends StatefulWidget {
  final List<Memory> memories;
  final MemoriesProvider provider;
  final VoidCallback onClose;

  const DesktopMemoryReviewSheet({
    super.key,
    required this.memories,
    required this.provider,
    required this.onClose,
  });

  @override
  State<DesktopMemoryReviewSheet> createState() => _DesktopMemoryReviewSheetState();
}

class _DesktopMemoryReviewSheetState extends State<DesktopMemoryReviewSheet> with SingleTickerProviderStateMixin {
  late List<Memory> remainingMemories;
  late List<Memory> displayedMemories;
  MemoryCategory? selectedCategory;
  bool _isProcessing = false;
  late AnimationController _animationController;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    remainingMemories = List.from(widget.memories);
    displayedMemories = List.from(remainingMemories);

    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(1.0, 0.0),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    ));

    // Start animation
    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
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

    for (var memory in memoriesToProcess) {
      await Future.delayed(const Duration(milliseconds: 20));
      widget.provider.reviewMemory(memory, approve, 'desktop_review_panel_batch');
    }

    setState(() {
      remainingMemories.removeWhere((f) => memoriesToProcess.contains(f));
      displayedMemories = selectedCategory == null
          ? List.from(remainingMemories)
          : remainingMemories.where((f) => f.category == selectedCategory).toList();
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
      await _handleClose();
    }
  }

  void _processSingleMemory(Memory memory, bool approve) async {
    if (_isProcessing) return;

    setState(() => _isProcessing = true);

    widget.provider.reviewMemory(memory, approve, 'desktop_review_panel_single');

    setState(() {
      remainingMemories.remove(memory);
      displayedMemories = selectedCategory == null
          ? List.from(remainingMemories)
          : remainingMemories.where((f) => f.category == selectedCategory).toList();
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
      await _handleClose();
    }
  }

  Future<void> _handleClose() async {
    await _animationController.reverse();
    widget.onClose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return SlideTransition(
      position: _slideAnimation,
      child: FadeTransition(
        opacity: _fadeAnimation,
        child: Material(
          color: Colors.transparent,
          child: Container(
            width: responsive.responsiveWidth(
              baseWidth: 650,
              minWidth: 500,
              maxWidth: 750,
            ),
            height: double.infinity,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundPrimary,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 32,
                  offset: const Offset(-8, 0),
                ),
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.1),
                  blurRadius: 64,
                  offset: const Offset(-16, 0),
                ),
              ],
            ),
            child: Column(
              children: [
                _buildHeader(responsive),
                _buildFilterChips(responsive),
                Expanded(child: _buildContent(responsive)),
                if (displayedMemories.isNotEmpty && !_isProcessing) _buildBottomActions(responsive),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(ResponsiveHelper responsive) {
    return Container(
      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          OmiPanelHeader(
            icon: FontAwesomeIcons.magnifyingGlass,
            title: 'Review Memories',
            onClose: _handleClose,
            spacing: responsive.spacing(baseSpacing: 12),
          ),
          SizedBox(height: responsive.spacing(baseSpacing: 8)),
          Text(
            _getSubtitle(),
            style: responsive.bodyMedium.copyWith(
              color: ResponsiveHelper.textTertiary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChips(ResponsiveHelper responsive) {
    if (categoryCounts.isEmpty) return const SizedBox.shrink();

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: responsive.spacing(baseSpacing: 24),
        vertical: responsive.spacing(baseSpacing: 12),
      ),
      child: Align(
        alignment: Alignment.centerLeft,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildFilterChip(
                responsive,
                'All (${remainingMemories.length})',
                selectedCategory == null,
                () => _filterByCategory(null),
              ),
              SizedBox(width: responsive.spacing(baseSpacing: 8)),
              ...categoryCounts.entries.map((entry) {
                final category = entry.key;
                final count = entry.value;
                String categoryName = category.toString().split('.').last;
                categoryName = categoryName[0].toUpperCase() + categoryName.substring(1);

                return Padding(
                  padding: EdgeInsets.only(right: responsive.spacing(baseSpacing: 8)),
                  child: _buildFilterChip(
                    responsive,
                    '$categoryName ($count)',
                    selectedCategory == category,
                    () => _filterByCategory(category),
                  ),
                );
              }),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFilterChip(ResponsiveHelper responsive, String label, bool isSelected, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: responsive.spacing(baseSpacing: 16),
            vertical: responsive.spacing(baseSpacing: 8),
          ),
          decoration: BoxDecoration(
            color: isSelected
                ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.15)
                : ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isSelected
                  ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.4)
                  : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: Text(
            label,
            style: responsive.bodyMedium.copyWith(
              color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
              fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
            ),
            softWrap: false,
            textScaler: const TextScaler.linear(1.0),
          ),
        ),
      ),
    );
  }

  Widget _buildContent(ResponsiveHelper responsive) {
    if (displayedMemories.isEmpty) {
      return _buildEmptyState(responsive);
    }

    return ListView.separated(
      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
      itemCount: displayedMemories.length,
      separatorBuilder: (context, index) => SizedBox(height: responsive.spacing(baseSpacing: 12)),
      itemBuilder: (context, index) {
        final memory = displayedMemories[index];
        return _buildMemoryCard(responsive, memory);
      },
    );
  }

  Widget _buildEmptyState(ResponsiveHelper responsive) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 300),
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 32)),
        child: OmiEmptyState(
          icon: FontAwesomeIcons.circleCheck,
          title: selectedCategory == null ? 'All memories reviewed!' : 'No memories in this category',
          message: selectedCategory == null
              ? 'Great work! All memories have been processed.'
              : 'Try switching to a different category.',
          color: ResponsiveHelper.purplePrimary,
          iconSize: 32,
          iconPadding: responsive.spacing(baseSpacing: 16),
        ),
      ),
    );
  }

  Widget _buildMemoryCard(ResponsiveHelper responsive, Memory memory) {
    return Material(
      color: Colors.transparent,
      child: Container(
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Category indicator
            Container(
              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
              decoration: BoxDecoration(
                color: _getCategoryColor(memory.category).withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                _getCategoryIcon(memory.category),
                color: _getCategoryColor(memory.category),
                size: 16,
              ),
            ),

            SizedBox(width: responsive.spacing(baseSpacing: 12)),

            // Memory content
            Expanded(
              child: Text(
                memory.content.decodeString,
                style: responsive.bodyLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  height: 1.4,
                ),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ),

            SizedBox(width: responsive.spacing(baseSpacing: 12)),

            // Action buttons
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                OmiIconButton(
                  icon: FontAwesomeIcons.trash,
                  onPressed: () => _processSingleMemory(memory, false),
                  style: OmiIconButtonStyle.outline,
                  color: ResponsiveHelper.errorColor,
                  size: 32,
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                OmiIconButton(
                  icon: FontAwesomeIcons.check,
                  onPressed: () => _processSingleMemory(memory, true),
                  style: OmiIconButtonStyle.outline,
                  color: ResponsiveHelper.successColor,
                  size: 32,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomActions(ResponsiveHelper responsive) {
    return Container(
      padding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
        border: Border(
          top: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
      ),
      child: _isProcessing
          ? const Center(child: OmiLoadingBadge(label: 'Processing...'))
          : Row(
              children: [
                Expanded(
                  child: OmiButton(
                    label: 'Discard All',
                    icon: FontAwesomeIcons.trash,
                    onPressed: () => _processBatchAction(false),
                    type: OmiButtonType.text,
                  ),
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 12)),
                Expanded(
                  child: OmiButton(
                    label: 'Save All',
                    icon: FontAwesomeIcons.check,
                    onPressed: () => _processBatchAction(true),
                    type: OmiButtonType.primary,
                    color: ResponsiveHelper.successColor,
                  ),
                ),
              ],
            ),
    );
  }

  String _getSubtitle() {
    if (selectedCategory == null) {
      return '${displayedMemories.length} memories to review';
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
    }
  }

  Color _getCategoryColor(MemoryCategory category) {
    switch (category) {
      case MemoryCategory.interesting:
        return ResponsiveHelper.purplePrimary;
      case MemoryCategory.system:
        return Colors.orange;
    }
  }

  IconData _getCategoryIcon(MemoryCategory category) {
    switch (category) {
      case MemoryCategory.interesting:
        return FontAwesomeIcons.lightbulb;
      case MemoryCategory.system:
        return FontAwesomeIcons.gear;
    }
  }
}
