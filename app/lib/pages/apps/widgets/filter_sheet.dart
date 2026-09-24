import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';

/// The app store's filter sheet: authorship, rating, category, sort and capability filters, with
/// Reset and Apply at the bottom.
///
/// Present it with [FilterBottomSheet.show]; the sheet shell owns the handle, title and close X.
class FilterBottomSheet extends StatelessWidget {
  const FilterBottomSheet({super.key});

  static Future<void> show(BuildContext context) {
    return showOmiSheet<void>(
      context: context,
      title: AppLocalizations.of(context).filters,
      padding: EdgeInsets.zero,
      builder: (context) => const FilterBottomSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.75,
      child: Consumer<AppProvider>(
        builder: (context, provider, child) {
          return Column(
            children: [
              // Content
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.lg, OmiSpacing.xl),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Apps
                      _buildSectionTitle(AppLocalizations.of(context).apps),
                      const SizedBox(height: OmiSpacing.xs),
                      _buildAuthorshipChip(context, provider),

                      const SizedBox(height: OmiSpacing.xl),

                      // Rating
                      _buildSectionTitle(AppLocalizations.of(context).rating),
                      const SizedBox(height: OmiSpacing.sm),
                      _buildRatingSelector(provider),

                      const SizedBox(height: OmiSpacing.xl),

                      // Categories
                      _buildSectionTitle(AppLocalizations.of(context).categories),
                      const SizedBox(height: OmiSpacing.xs),
                      _buildCategoryChips(context, provider),

                      const SizedBox(height: OmiSpacing.xl),

                      // Sort Options
                      _buildSectionTitle(AppLocalizations.of(context).sortBy),
                      const SizedBox(height: OmiSpacing.sm),
                      _buildSortOptions(context, provider),

                      const SizedBox(height: OmiSpacing.xl),

                      // Capabilities
                      _buildSectionTitle(AppLocalizations.of(context).capabilities),
                      const SizedBox(height: OmiSpacing.xs),
                      _buildCapabilities(context, provider),
                    ],
                  ),
                ),
              ),

              // Bottom buttons
              Container(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.lg, OmiSpacing.xs),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: OmiColors.border, width: 1)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: OmiButton.secondary(
                        key: const ValueKey('filter_sheet_reset_button'),
                        label: AppLocalizations.of(context).resetFilters,
                        expand: true,
                        onPressed: () {
                          provider.clearFilters();
                          PlatformManager.instance.analytics.appsClearFilters();
                          Navigator.of(context).pop();
                          Future.microtask(() => provider.applyFilters());
                        },
                      ),
                    ),
                    const SizedBox(width: OmiSpacing.md),
                    Expanded(
                      child: OmiButton(
                        key: const ValueKey('filter_sheet_apply_button'),
                        label: AppLocalizations.of(context).applyFilters,
                        expand: true,
                        onPressed: () {
                          Navigator.of(context).pop();
                          Future.microtask(() => provider.applyFilters());
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white),
    );
  }

  Widget _buildRatingSelector(AppProvider provider) {
    final ratings = ['1', '2', '3', '4', '5'];

    return Row(
      children: ratings.map((rating) {
        final filterKey = '$rating+ Stars';
        final isSelected = provider.isFilterSelected(filterKey, 'Rating');

        return Expanded(
          child: GestureDetector(
            onTap: () {
              provider.addOrRemoveFilter(filterKey, 'Rating');
              PlatformManager.instance.analytics.appsRatingFilter(
                filterKey,
                provider.isFilterSelected(filterKey, 'Rating'),
              );
            },
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(
                color: isSelected ? Colors.white.withValues(alpha: 0.22) : const Color(0xFF35343B),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  '$rating+',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: isSelected ? Colors.white : Colors.grey.shade400,
                  ),
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildAuthorshipChip(BuildContext context, AppProvider provider) {
    final isSelected = provider.isFilterSelected('My Apps', 'Apps');

    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        GestureDetector(
          onTap: () {
            provider.addOrRemoveFilter('My Apps', 'Apps');
            provider.applyFilters();
            PlatformManager.instance.analytics.appsTypeFilter('My Apps', !isSelected);
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: isSelected ? Colors.white.withValues(alpha: 0.22) : const Color(0xFF35343B),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              AppLocalizations.of(context).myApps,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: isSelected ? Colors.white : Colors.grey.shade300,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCategoryChips(BuildContext context, AppProvider provider) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: provider.categories.map((category) {
        final isSelected = provider.isCategoryFilterSelected(category);

        return GestureDetector(
          onTap: () {
            provider.addOrRemoveCategoryFilter(category);
            PlatformManager.instance.analytics.appsCategoryFilter(
              category.title,
              provider.isCategoryFilterSelected(category),
            );
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: isSelected ? Colors.white.withValues(alpha: 0.22) : const Color(0xFF35343B),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              category.getLocalizedTitle(context),
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: isSelected ? Colors.white : Colors.grey.shade300,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildSortOptions(BuildContext context, AppProvider provider) {
    final l10n = AppLocalizations.of(context);
    final sortOptions = [
      {'label': 'A-Z', 'key': 'A-Z'},
      {'label': 'Z-A', 'key': 'Z-A'},
      {'label': l10n.highestRating, 'key': 'Highest Rating'},
      {'label': l10n.lowestRating, 'key': 'Lowest Rating'},
      {'label': l10n.mostInstalls, 'key': 'Most Installs'},
    ];

    return Column(
      children: sortOptions.map((option) {
        final isSelected = provider.isFilterSelected(option['key']!, 'Sort');

        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          child: GestureDetector(
            onTap: () {
              provider.addOrRemoveFilter(option['key']!, 'Sort');
              PlatformManager.instance.analytics.appsSortFilter(
                option['key']!,
                provider.isFilterSelected(option['key']!, 'Sort'),
              );
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25).withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(12),
                border: isSelected ? Border.all(color: Colors.white, width: 2) : null,
              ),
              child: Row(
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isSelected ? Colors.white : Colors.transparent,
                      border: Border.all(color: isSelected ? Colors.white : Colors.grey.shade500, width: 2),
                    ),
                    child: isSelected ? const Icon(Icons.check, size: 12, color: Colors.black) : null,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    option['label']!,
                    style: TextStyle(
                      fontSize: 16,
                      color: isSelected ? Colors.white : Colors.grey.shade300,
                      fontWeight: isSelected ? FontWeight.w500 : FontWeight.normal,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildCapabilities(BuildContext context, AppProvider provider) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: provider.capabilities.map((capability) {
        final isSelected = provider.isCapabilityFilterSelected(capability);

        return GestureDetector(
          onTap: () {
            provider.addOrRemoveCapabilityFilter(capability);
            PlatformManager.instance.analytics.appsCapabilityFilter(
              capability.title,
              provider.isCapabilityFilterSelected(capability),
            );
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: isSelected ? Colors.white.withValues(alpha: 0.22) : const Color(0xFF35343B),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              capability.getLocalizedTitle(context),
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: isSelected ? Colors.white : Colors.grey.shade300,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}
