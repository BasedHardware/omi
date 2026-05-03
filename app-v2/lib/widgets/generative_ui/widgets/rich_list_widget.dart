import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/rich_list_item_data.dart';

/// Horizontal scrollable list widget for rendering rich items with images.
class RichListWidget extends StatelessWidget {
  final List<RichListItemData> items;
  final void Function(String url)? onUrlTap;

  const RichListWidget({super.key, required this.items, this.onUrlTap});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      height: 240,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXS),
        itemBuilder: (context, index) {
          final item = items[index];
          return _RichListCard(data: item, onTap: item.hasUrl && onUrlTap != null ? () => onUrlTap!(item.url!) : null);
        },
      ),
    );
  }
}

class _RichListCard extends StatelessWidget {
  final RichListItemData data;
  final VoidCallback? onTap;

  const _RichListCard({required this.data, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 200,
      margin: const EdgeInsets.symmetric(horizontal: 6),
      child: Material(
        color: Colors.transparent,
        child: onTap != null
            ? InkWell(
                onTap: onTap,
                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                child: _buildCardContent(),
              )
            : _buildCardContent(),
      ),
    );
  }

  Widget _buildCardContent() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 5, child: _buildImage()),
          Expanded(
            flex: 4,
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    data.title,
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      height: 1.2,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (data.description != null && data.description!.isNotEmpty) ...[
                    const SizedBox(height: AppStyles.spacingXS),
                    Expanded(
                      child: Text(
                        data.description!,
                        style: const TextStyle(color: AppColors.textTertiary, fontSize: 11, height: 1.3),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildImage() {
    if (!data.hasThumbnail) {
      return Container(
        color: AppColors.backgroundTertiary,
        child: const Center(child: Icon(Icons.image_outlined, color: AppColors.textQuaternary, size: 32)),
      );
    }

    return CachedNetworkImage(
      imageUrl: data.thumbnailUrl!,
      fit: BoxFit.cover,
      width: double.infinity,
      placeholder: (context, url) => Container(
        color: AppColors.backgroundTertiary,
        child: const Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.textTertiary),
            ),
          ),
        ),
      ),
      errorWidget: (context, url, error) => Container(
        color: AppColors.backgroundTertiary,
        child: const Center(child: Icon(Icons.broken_image_outlined, color: AppColors.textQuaternary, size: 32)),
      ),
    );
  }
}
