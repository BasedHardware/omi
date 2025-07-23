import 'package:flutter/material.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

class FilterBottomSheet extends StatelessWidget {
  const FilterBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.85,
      decoration: const BoxDecoration(
        color: Color(0xFF1C1C1E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Consumer<AppProvider>(
        builder: (context, provider, child) {
          return Column(
            children: [
              // Header
              Container(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                child: Row(
                  children: [
                    Text(
                      'Filters',
                      style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                    if (provider.filters.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Color(0xFF8B5CF6),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          '${provider.filters.length}',
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ],
                    const Spacer(),
                    IconButton(
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(
                        Icons.close,
                        color: Colors.white,
                        size: 24,
                      ),
                    ),
                  ],
                ),
              ),

              // Divider
              Container(
                margin: const EdgeInsets.symmetric(vertical: 16),
                height: 1,
                color: Color(0xFF35343B),
              ),

              // Content
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // App Type Toggle
                      _buildSectionTitle('App Type'),
                      const SizedBox(height: 12),
                      _buildToggleOption(
                        'Show my apps',
                        provider.isFilterSelected('My Apps', 'Apps'),
                        () {
                          provider.addOrRemoveFilter('My Apps', 'Apps');
                          MixpanelManager().appsTypeFilter('My Apps', provider.isFilterSelected('My Apps', 'Apps'));
                        },
                      ),
                      const SizedBox(height: 8),
                      _buildToggleOption(
                        'Show installed apps',
                        provider.isFilterSelected('Installed Apps', 'Apps'),
                        () {
                          provider.addOrRemoveFilter('Installed Apps', 'Apps');
                          MixpanelManager().appsTypeFilter('Installed Apps', provider.isFilterSelected('Installed Apps', 'Apps'));
                        },
                      ),

                      const SizedBox(height: 32),

                      // Rating
                      _buildSectionTitle('Rating'),
                      const SizedBox(height: 12),
                      _buildRatingSelector(provider),

                      const SizedBox(height: 32),

                      // Categories
                      _buildSectionTitle('Categories'),
                      const SizedBox(height: 12),
                      _buildCategoryChips(provider),

                      const SizedBox(height: 32),

                      // Sort Options
                      _buildSectionTitle('Sort'),
                      const SizedBox(height: 12),
                      _buildSortOptions(provider),

                      const SizedBox(height: 32),

                      // Capabilities
                      _buildSectionTitle('Capabilities'),
                      const SizedBox(height: 12),
                      _buildCapabilities(provider),

                      const SizedBox(height: 100), // Extra space for bottom buttons
                    ],
                  ),
                ),
              ),

              // Bottom buttons
              Container(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
                decoration: BoxDecoration(
                  color: const Color(0xFF1C1C1E),
                  border: Border(
                    top: BorderSide(color: Color(0xFF35343B), width: 1),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: TextButton(
                        onPressed: () {
                          provider.clearFilters();
                          MixpanelManager().appsClearFilters();
                        },
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                            side: BorderSide(color: Colors.grey.shade600),
                          ),
                        ),
                        child: const Text(
                          'Reset filters',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          provider.filterApps();
                          Navigator.of(context).pop();
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: const Text(
                          'Apply filters',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: Colors.black,
                          ),
                        ),
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
      style: const TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: Colors.white,
      ),
    );
  }

  Widget _buildToggleOption(String title, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25).withOpacity(0.5),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 16,
                color: Colors.white,
              ),
            ),
            const Spacer(),
            Switch(
              value: isSelected,
              onChanged: (value) => onTap(),
              activeColor: Color(0xFF8B5CF6),
              inactiveThumbColor: Colors.grey.shade400,
              inactiveTrackColor: Colors.grey.shade700,
            ),
          ],
        ),
      ),
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
              MixpanelManager().appsRatingFilter(filterKey, provider.isFilterSelected(filterKey, 'Rating'));
            },
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(
                color: isSelected ? Color(0xFF8B5CF6) : Color(0xFF35343B),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(
                child: Text(
                  rating,
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

  Widget _buildCategoryChips(AppProvider provider) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: provider.categories.map((category) {
        final isSelected = provider.isCategoryFilterSelected(category);

        return GestureDetector(
          onTap: () {
            provider.addOrRemoveCategoryFilter(category);
            MixpanelManager().appsCategoryFilter(category.title, provider.isCategoryFilterSelected(category));
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: isSelected ? Color(0xFF8B5CF6) : Color(0xFF35343B),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              category.title,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: isSelected ? Colors.white : Colors.grey.shade300,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildSortOptions(AppProvider provider) {
    final sortOptions = [
      {'label': 'A-Z', 'key': 'A-Z'},
      {'label': 'Z-A', 'key': 'Z-A'},
      {'label': 'Highest Rating', 'key': 'Highest Rating'},
      {'label': 'Lowest Rating', 'key': 'Lowest Rating'},
    ];

    return Column(
      children: sortOptions.map((option) {
        final isSelected = provider.isFilterSelected(option['key']!, 'Sort');

        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          child: GestureDetector(
            onTap: () {
              provider.addOrRemoveFilter(option['key']!, 'Sort');
              MixpanelManager().appsSortFilter(option['key']!, provider.isFilterSelected(option['key']!, 'Sort'));
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25).withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
                border: isSelected ? Border.all(color: Color(0xFF8B5CF6), width: 2) : null,
              ),
              child: Row(
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isSelected ? Color(0xFF8B5CF6) : Colors.transparent,
                      border: Border.all(
                        color: isSelected ? Color(0xFF8B5CF6) : Colors.grey.shade500,
                        width: 2,
                      ),
                    ),
                    child: isSelected
                        ? const Icon(
                            Icons.check,
                            size: 12,
                            color: Colors.white,
                          )
                        : null,
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

  Widget _buildCapabilities(AppProvider provider) {
    return Column(
      children: provider.capabilities.map((capability) {
        final isSelected = provider.isCapabilityFilterSelected(capability);

        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          child: GestureDetector(
            onTap: () {
              provider.addOrRemoveCapabilityFilter(capability);
              MixpanelManager().appsCapabilityFilter(capability.title, provider.isCapabilityFilterSelected(capability));
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25).withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(4),
                      color: isSelected ? Color(0xFF8B5CF6) : Colors.transparent,
                      border: Border.all(
                        color: isSelected ? Color(0xFF8B5CF6) : Colors.grey.shade500,
                        width: 2,
                      ),
                    ),
                    child: isSelected
                        ? const Icon(
                            Icons.check,
                            size: 12,
                            color: Colors.white,
                          )
                        : null,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    capability.title,
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
}
