import 'package:flutter/material.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:provider/provider.dart';

class FilterBottomSheet extends StatelessWidget {
  const FilterBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      maxChildSize: 0.8,
      initialChildSize: 0.6,
      minChildSize: 0.4,
      builder: (context, scrollController) {
        return Consumer<AppProvider>(builder: (context, provider, child) {
          return Scaffold(
            body: SingleChildScrollView(
              controller: scrollController,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Filters',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close),
                          onPressed: () {
                            provider.filterApps();
                            Navigator.of(context).pop();
                          },
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    FilterSection(
                      title: 'Apps',
                      child: Column(
                        children: [
                          FilterOption(
                            label: 'Installed Apps',
                            onTap: () {
                              provider.addOrRemoveFilter('Installed Apps', 'Apps');
                            },
                            isSelected: provider.isFilterSelected('Installed Apps', 'Apps'),
                          ),
                          FilterOption(
                            label: 'My Apps',
                            onTap: () {
                              provider.addOrRemoveFilter('My Apps', 'Apps');
                            },
                            isSelected: provider.isFilterSelected('My Apps', 'Apps'),
                          ),
                        ],
                      ),
                    ),
                    FilterSection(
                        title: 'Sort',
                        child: Column(
                          children: [
                            FilterOption(
                              label: 'A-Z',
                              onTap: () {
                                provider.addOrRemoveFilter('A-Z', 'Sort');
                              },
                              isSelected: provider.isFilterSelected('A-Z', 'Sort'),
                            ),
                            FilterOption(
                              label: 'Z-A',
                              onTap: () {
                                provider.addOrRemoveFilter('Z-A', 'Sort');
                              },
                              isSelected: provider.isFilterSelected('Z-A', 'Sort'),
                            ),
                            FilterOption(
                              label: 'Highest Rating',
                              onTap: () {
                                provider.addOrRemoveFilter('Highest Rating', 'Sort');
                              },
                              isSelected: provider.isFilterSelected('Highest Rating', 'Sort'),
                            ),
                            FilterOption(
                              label: 'Lowest Rating',
                              onTap: () {
                                provider.addOrRemoveFilter('Lowest Rating', 'Sort');
                              },
                              isSelected: provider.isFilterSelected('Lowest Rating', 'Sort'),
                            ),
                          ],
                        )),
                    FilterSection(
                      title: 'Category',
                      child: Column(
                        children: provider.categories
                            .map((category) => FilterOption(
                                  label: category.title,
                                  onTap: () {
                                    provider.addOrRemoveCategoryFilter(category);
                                  },
                                  isSelected: provider.isCategoryFilterSelected(category),
                                ))
                            .toList(),
                      ),
                    ),
                    FilterSection(
                      title: 'Rating',
                      child: Column(
                        children: [
                          FilterOption(
                              label: '1+ Stars',
                              onTap: () {
                                provider.addOrRemoveFilter('1+ Stars', 'Rating');
                              },
                              isSelected: provider.isFilterSelected('1+ Stars', 'Rating')),
                          FilterOption(
                              label: '2+ Stars',
                              onTap: () {
                                provider.addOrRemoveFilter('2+ Stars', 'Rating');
                              },
                              isSelected: provider.isFilterSelected('2+ Stars', 'Rating')),
                          FilterOption(
                              label: '3+ Stars',
                              onTap: () {
                                provider.addOrRemoveFilter('3+ Stars', 'Rating');
                              },
                              isSelected: provider.isFilterSelected('3+ Stars', 'Rating')),
                          FilterOption(
                              label: '4+ Stars',
                              onTap: () {
                                provider.addOrRemoveFilter('4+ Stars', 'Rating');
                              },
                              isSelected: provider.isFilterSelected('4+ Stars', 'Rating')),
                        ],
                      ),
                    ),
                    FilterSection(
                      title: 'Capabilities',
                      child: Column(
                        children: provider.capabilities
                            .map((capability) => FilterOption(
                                  label: capability.title,
                                  onTap: () {
                                    provider.addOrRemoveCapabilityFilter(capability);
                                  },
                                  isSelected: provider.isCapabilityFilterSelected(capability),
                                ))
                            .toList(),
                      ),
                    ),
                    const SizedBox(height: 20),
                  ],
                ),
              ),
            ),
            bottomNavigationBar: Padding(
              padding: const EdgeInsets.fromLTRB(40, 10, 40, 40),
              child: ElevatedButton(
                onPressed: () {
                  provider.clearFilters();
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.grey[300],
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
                child: const Text('Clear Filters'),
              ),
            ),
          );
        });
      },
    );
  }
}

class FilterSection extends StatelessWidget {
  final String title;
  final Widget? child;

  const FilterSection({super.key, required this.title, this.child});

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      iconColor: Colors.white,
      title: Text(
        title,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w500, color: Colors.white),
      ),
      children: [if (child != null) child!],
    );
  }
}

class FilterOption extends StatelessWidget {
  final String label;
  final Function()? onTap;
  final bool isSelected;

  const FilterOption({super.key, required this.label, this.onTap, this.isSelected = false});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: SizedBox(
        height: 22.0,
        width: 22.0,
        child: Checkbox(
          shape: const CircleBorder(),
          value: isSelected,
          onChanged: (value) {
            if (onTap != null) {
              onTap!();
            }
          },
        ),
      ),
      title: Text(label),
      onTap: onTap,
    );
  }
}
