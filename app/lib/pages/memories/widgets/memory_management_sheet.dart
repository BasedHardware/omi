import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/ui_guidelines.dart';

class MemoryManagementSheet extends StatelessWidget {
  final MemoriesProvider provider;

  const MemoryManagementSheet({super.key, required this.provider});

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, child) {
        return SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildFilterSection(context),
              const Divider(height: 1, color: OmiColors.border),
              _buildMemoryCount(context),
              _buildActionButtons(context),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFilterSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 16, 8),
          child: OmiSectionHeader(context.l10n.filterMemories),
        ),
        _buildCategoryFilterOption(context, context.l10n.filterAll, null),
        _buildCategoryFilterOption(context, context.l10n.filterSystem, MemoryCategory.system),
        _buildCategoryFilterOption(context, context.l10n.filterInteresting, MemoryCategory.interesting),
        _buildCategoryFilterOption(context, context.l10n.filterManual, MemoryCategory.manual),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Divider(height: 1, color: Colors.white10),
        ),
        if (provider.memoryBeliefEnabled) ...[
          _buildFilterOption(
            context,
            context.l10n.current,
            isSelected: provider.collectionView == MemoryCollectionView.usefulNow,
            onTap: () => provider.setCollectionView(MemoryCollectionView.usefulNow),
          ),
          _buildFilterOption(
            context,
            context.l10n.memoryHistory,
            isSelected: provider.collectionView == MemoryCollectionView.history,
            onTap: () => provider.setCollectionView(MemoryCollectionView.history),
          ),
          _buildFilterOption(
            context,
            context.l10n.allMemories,
            isSelected: provider.collectionView == MemoryCollectionView.all,
            onTap: () => provider.setCollectionView(MemoryCollectionView.all),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            child: Divider(height: 1, color: Colors.white10),
          ),
        ],
        _buildFilterOption(
          context,
          context.l10n.memoryThisDevice,
          isSelected: provider.filterThisDeviceOnly,
          onTap: () => provider.setFilterThisDeviceOnly(!provider.filterThisDeviceOnly),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildCategoryFilterOption(BuildContext context, String label, MemoryCategory? category) {
    // If category is null, it represents "All"
    // For "All", it is selected if the set is empty.
    final bool isSelected;
    if (category == null) {
      isSelected = provider.selectedCategories.isEmpty;
    } else {
      isSelected = provider.selectedCategories.contains(category);
    }

    return _buildFilterOption(
      context,
      label,
      isSelected: isSelected,
      onTap: () {
        if (category == null) {
          provider.clearCategoryFilter();
        } else {
          provider.toggleCategoryFilter(category);
        }
        // Do NOT pop here to allow multiple selections
      },
    );
  }

  Widget _buildFilterOption(
    BuildContext context,
    String label, {
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      selected: isSelected,
      button: true,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: OmiType.callout.copyWith(fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400),
                  ),
                ),
                if (isSelected) const Icon(Icons.check, color: OmiColors.accent, size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMemoryCount(BuildContext context) {
    final totalMemories = provider.memories.length;
    final publicMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'public').length;
    final privateMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'private').length;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(context.l10n.totalMemoriesCount(totalMemories), style: AppStyles.body),
          const SizedBox(height: 8),
          _buildMemoryCountRow(Icons.public, context.l10n.publicMemories, publicMemories),
          const SizedBox(height: 4),
          _buildMemoryCountRow(Icons.lock_outline, context.l10n.privateMemories, privateMemories),
        ],
      ),
    );
  }

  Widget _buildMemoryCountRow(IconData icon, String label, int count) {
    return Row(
      children: [
        Icon(icon, size: 16, color: OmiColors.textSecondary),
        const SizedBox(width: 8),
        Text(label, style: AppStyles.caption),
        const Spacer(),
        Text(count.toString(), style: AppStyles.caption.copyWith(fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _buildActionButtons(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          OmiButton.secondary(
            label: context.l10n.makeAllPrivate,
            icon: Icons.lock_outline,
            expand: true,
            onPressed: () {
              _makeAllMemoriesPrivate(context);
            },
          ),
          const SizedBox(height: 12),
          OmiButton.secondary(
            label: context.l10n.makeAllPublic,
            icon: Icons.public,
            expand: true,
            onPressed: () {
              _makeAllMemoriesPublic(context);
            },
          ),
          const SizedBox(height: 24),
          const Divider(height: 1, color: OmiColors.border),
          const SizedBox(height: 24),
          OmiButton.destructive(
            label: context.l10n.deleteAllMemories,
            icon: Icons.delete_outline,
            expand: true,
            // Not awaited: the button would spin for as long as the confirmation is open.
            onPressed: () {
              _confirmDeleteAllMemories(context);
            },
          ),
        ],
      ),
    );
  }

  Future<void> _makeAllMemoriesPrivate(BuildContext context) => _setAllVisibility(context, private: true);

  Future<void> _makeAllMemoriesPublic(BuildContext context) => _setAllVisibility(context, private: false);

  Future<void> _setAllVisibility(BuildContext context, {required bool private}) async {
    // The sheet closes first; the result toast goes to the page underneath, so keep hold of a
    // context that outlives the sheet.
    final pageContext = Navigator.of(context).context;
    Navigator.pop(context);
    final updated = await provider.updateAllMemoriesVisibility(private);
    if (!pageContext.mounted) return;
    final l10n = pageContext.l10n;
    if (updated) {
      OmiFeedback.confirm(pageContext, private ? l10n.allMemoriesPrivateResult : l10n.allMemoriesPublicResult);
    } else {
      OmiFeedback.error(pageContext, l10n.somethingWentWrong);
    }
  }

  Future<void> _confirmDeleteAllMemories(BuildContext context) async {
    final pageContext = Navigator.of(context).context;
    if (provider.memories.isEmpty) {
      Navigator.pop(context);
      OmiFeedback.info(pageContext, pageContext.l10n.noMemoriesToDelete);
      return;
    }

    // Cannot be undone: confirm every time (docs/ux-contract.md §4).
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.clearMemoryTitle,
      message: context.l10n.clearMemoryMessage,
      confirmLabel: context.l10n.clearMemoryButton,
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    Navigator.pop(context); // Close sheet
    final cleared = await provider.deleteAllMemories();
    if (!pageContext.mounted) return;
    if (cleared) {
      OmiFeedback.confirm(pageContext, pageContext.l10n.memoryClearedSuccess);
    } else {
      OmiFeedback.error(pageContext, pageContext.l10n.somethingWentWrong);
    }
  }
}
