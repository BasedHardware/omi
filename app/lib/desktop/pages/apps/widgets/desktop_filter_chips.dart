import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/atoms/omi_choice_chip.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/ui/molecules/omi_popup_menu.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopFilterChips extends StatelessWidget {
  final VoidCallback onFilterChanged;

  const DesktopFilterChips({
    super.key,
    required this.onFilterChanged,
  });

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Consumer<AppProvider>(
      builder: (context, appProvider, _) {
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              // App Type Filters
              _buildFilterChip(
                responsive: responsive,
                label: context.l10n.filterInstalled,
                isSelected: appProvider.isFilterSelected('Installed Apps', 'Apps'),
                onTap: () {
                  appProvider.addOrRemoveFilter('Installed Apps', 'Apps');
                  MixpanelManager().appsTypeFilter(
                    'Installed Apps',
                    appProvider.isFilterSelected('Installed Apps', 'Apps'),
                  );
                  onFilterChanged();
                },
              ),

              SizedBox(width: responsive.spacing(baseSpacing: 12)),

              _buildFilterChip(
                responsive: responsive,
                label: context.l10n.filterMyApps,
                isSelected: appProvider.isFilterSelected('My Apps', 'Apps'),
                onTap: () {
                  appProvider.addOrRemoveFilter('My Apps', 'Apps');
                  MixpanelManager().appsTypeFilter(
                    'My Apps',
                    appProvider.isFilterSelected('My Apps', 'Apps'),
                  );
                  onFilterChanged();
                },
              ),

              // Separator
              Container(
                margin: EdgeInsets.symmetric(
                  horizontal: responsive.spacing(baseSpacing: 16),
                ),
                width: 1,
                height: 24,
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
              ),

              // Category Dropdown
              _buildCategoryDropdown(responsive, appProvider),

              SizedBox(width: responsive.spacing(baseSpacing: 12)),

              // Rating Dropdown
              _buildRatingDropdown(responsive, appProvider),

              SizedBox(width: responsive.spacing(baseSpacing: 12)),

              // Capabilities Dropdown
              _buildCapabilitiesDropdown(responsive, appProvider),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFilterChip({
    required ResponsiveHelper responsive,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return OmiChoiceChip(
      label: label,
      selected: isSelected,
      onTap: onTap,
    );
  }

  Widget _buildCategoryDropdown(ResponsiveHelper responsive, AppProvider appProvider) {
    if (appProvider.categories.isEmpty) {
      return const SizedBox.shrink();
    }

    final selectedCategory = appProvider.filters['Category'];

    return Builder(
      builder: (context) => OmiPopupMenuButton<dynamic>(
        itemBuilder: (context) => [
          if (selectedCategory != null)
            PopupMenuItem(
              value: 'clear',
              child: Row(
                children: [
                  const Icon(Icons.clear, size: 16, color: ResponsiveHelper.textTertiary),
                  const SizedBox(width: 8),
                  Text(context.l10n.clearSelection,
                      style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textTertiary)),
                ],
              ),
            ),
          if (selectedCategory != null) const PopupMenuDivider(),
          ...appProvider.categories.map((category) => PopupMenuItem(
              value: category,
              child: Text(category.getLocalizedTitle(context),
                  style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textSecondary))))
        ],
        onSelected: (value) {
          if (value == 'clear') {
            appProvider.removeFilter('Category');
          } else {
            appProvider.addOrRemoveCategoryFilter(value);
            MixpanelManager().appsCategoryFilter(value.title, true);
          }
          onFilterChanged();
        },
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: responsive.spacing(baseSpacing: 16),
            vertical: responsive.spacing(baseSpacing: 8),
          ),
          decoration: BoxDecoration(
            color: selectedCategory != null
                ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                : ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selectedCategory != null
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.4)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                selectedCategory?.title ?? context.l10n.filterCategory,
                style: responsive.bodyMedium.copyWith(
                  color: selectedCategory != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  fontWeight: selectedCategory != null ? FontWeight.w500 : FontWeight.w400,
                ),
              ),
              SizedBox(width: responsive.spacing(baseSpacing: 6)),
              Icon(
                Icons.keyboard_arrow_down_rounded,
                size: 18,
                color: selectedCategory != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRatingDropdown(ResponsiveHelper responsive, AppProvider appProvider) {
    return Builder(
      builder: (context) {
        final ratingOptions = [
          context.l10n.rating4PlusStars,
          context.l10n.rating3PlusStars,
          context.l10n.rating2PlusStars,
          context.l10n.rating1PlusStars
        ];
        final ratingKeys = ['4+ Stars', '3+ Stars', '2+ Stars', '1+ Stars'];
        final selectedRating = appProvider.filters['Rating'];

        return OmiPopupMenuButton<String>(
          itemBuilder: (context) => [
            if (selectedRating != null)
              PopupMenuItem(
                  value: 'clear',
                  child: Row(children: [
                    const Icon(Icons.clear, size: 16, color: ResponsiveHelper.textTertiary),
                    const SizedBox(width: 8),
                    Text(context.l10n.clearSelection,
                        style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textTertiary))
                  ])),
            if (selectedRating != null) const PopupMenuDivider(),
            ...List.generate(
                ratingOptions.length,
                (index) => PopupMenuItem(
                    value: ratingKeys[index],
                    child: Row(children: [
                      const Icon(Icons.star_rounded, size: 16, color: ResponsiveHelper.purplePrimary),
                      const SizedBox(width: 8),
                      Text(ratingOptions[index],
                          style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textSecondary))
                    ]))),
          ],
          onSelected: (value) {
            if (value == 'clear') {
              appProvider.removeFilter('Rating');
            } else {
              appProvider.addOrRemoveFilter(value, 'Rating');
              MixpanelManager().appsRatingFilter(value, true);
            }
            onFilterChanged();
          },
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: responsive.spacing(baseSpacing: 16),
              vertical: responsive.spacing(baseSpacing: 8),
            ),
            decoration: BoxDecoration(
              color: selectedRating != null
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                  : ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: selectedRating != null
                    ? ResponsiveHelper.purplePrimary.withOpacity(0.4)
                    : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  selectedRating != null
                      ? ratingOptions[ratingKeys.indexOf(selectedRating)]
                      : context.l10n.filterRating,
                  style: responsive.bodyMedium.copyWith(
                    color: selectedRating != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                    fontWeight: selectedRating != null ? FontWeight.w500 : FontWeight.w400,
                  ),
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 6)),
                Icon(
                  Icons.keyboard_arrow_down_rounded,
                  size: 18,
                  color: selectedRating != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildCapabilitiesDropdown(ResponsiveHelper responsive, AppProvider appProvider) {
    if (appProvider.capabilities.isEmpty) {
      return const SizedBox.shrink();
    }

    final selectedCapability = appProvider.filters['Capabilities'];

    return Builder(
      builder: (context) => OmiPopupMenuButton<dynamic>(
        itemBuilder: (context) => [
          if (selectedCapability != null)
            PopupMenuItem(
                value: 'clear',
                child: Row(children: [
                  const Icon(Icons.clear, size: 16, color: ResponsiveHelper.textTertiary),
                  const SizedBox(width: 8),
                  Text(context.l10n.clearSelection,
                      style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textTertiary))
                ])),
          if (selectedCapability != null) const PopupMenuDivider(),
          ...appProvider.capabilities.map((cap) => PopupMenuItem(
              value: cap,
              child: Text(cap.title, style: responsive.bodyMedium.copyWith(color: ResponsiveHelper.textSecondary))))
        ],
        onSelected: (value) {
          if (value == 'clear') {
            appProvider.removeFilter('Capabilities');
          } else {
            appProvider.addOrRemoveCapabilityFilter(value);
            MixpanelManager().appsCapabilityFilter(value.title, true);
          }
          onFilterChanged();
        },
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: responsive.spacing(baseSpacing: 16),
            vertical: responsive.spacing(baseSpacing: 8),
          ),
          decoration: BoxDecoration(
            color: selectedCapability != null
                ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                : ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: selectedCapability != null
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.4)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                selectedCapability?.title ?? context.l10n.filterCapabilities,
                style: responsive.bodyMedium.copyWith(
                  color: selectedCapability != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  fontWeight: selectedCapability != null ? FontWeight.w500 : FontWeight.w400,
                ),
              ),
              SizedBox(width: responsive.spacing(baseSpacing: 6)),
              Icon(
                Icons.keyboard_arrow_down_rounded,
                size: 18,
                color: selectedCapability != null ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
