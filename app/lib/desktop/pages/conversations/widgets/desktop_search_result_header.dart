import 'package:flutter/material.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

/// Premium minimal search result header for desktop
class DesktopSearchResultHeader extends StatelessWidget {
  const DesktopSearchResultHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, child) {
        var onSearches = provider.previousQuery.isNotEmpty;
        var isSearching = provider.isFetchingConversations;

        if (!onSearches) {
          return const SizedBox.shrink();
        }

        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 16),
          child: isSearching
              ? _buildShimmerEffect()
              : provider.totalSearchPages > 0
                  ? _buildSearchResults(provider)
                  : const SizedBox.shrink(),
        );
      },
    );
  }

  Widget _buildShimmerEffect() {
    return Shimmer.fromColors(
      baseColor: ResponsiveHelper.textTertiary,
      highlightColor: ResponsiveHelper.textQuaternary,
      child: Container(
        width: 180,
        height: 16,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary,
          borderRadius: BorderRadius.circular(4),
        ),
      ),
    );
  }

  Widget _buildSearchResults(ConversationProvider provider) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: BorderRadius.circular(6),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.search_rounded,
                size: 14,
                color: ResponsiveHelper.textTertiary,
              ),
              const SizedBox(width: 6),
              Text(
                'Search results',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textTertiary,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        Text(
          '"${provider.previousQuery}"',
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: ResponsiveHelper.textSecondary,
            fontStyle: FontStyle.italic,
          ),
        ),
      ],
    );
  }
}
